package selfupdate

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"time"
)

const (
	// ListTimeout bounds the release list request of the daily check.
	ListTimeout = 5 * time.Second
	// InstallTimeout bounds the download and the install of the daily check.
	InstallTimeout = 60 * time.Second
	// UpgradeListTimeout bounds the release list request of argus upgrade.
	UpgradeListTimeout = 30 * time.Second
	// UpgradeInstallTimeout bounds the download and the install of argus upgrade.
	UpgradeInstallTimeout = 5 * time.Minute
)

var (
	// ErrDevBuild is returned when a dev build is asked to upgrade.
	ErrDevBuild = errors.New("dev builds do not upgrade")
	// ErrBinaryReplaced is returned when another update replaced the binary after this process
	// started.
	ErrBinaryReplaced = errors.New("selfupdate: another update replaced the binary; run argus upgrade again")
)

// Result describes one update attempt.
type Result struct {
	From     string `json:"from"`
	To       string `json:"to"`
	Upgraded bool   `json:"upgraded"`
	Path     string `json:"path"`
}

// Updater finds and installs a newer CLI release over the running binary.
type Updater struct {
	current    string
	apiBase    string
	client     *http.Client
	goos       string
	goarch     string
	executable func() (string, error)
	stateDir   string
	now        func() time.Time
	// started returns the path and the file of the binary when the process started.
	started func() (string, os.FileInfo, error)
	geteuid func() int
}

// The path and the file of the running binary, read when the process starts. An update by
// another process renames a new file over the path, so the path then holds another file.
var startPath, startInfo, startErr = statExecutable(ExecutablePath)

func statExecutable(executable func() (string, error)) (string, os.FileInfo, error) {
	path, err := executable()
	if err != nil {
		return "", nil, err
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", nil, fmt.Errorf("%w: %w", ErrInstall, err)
	}
	return path, info, nil
}

// Option configures an Updater.
type Option func(*Updater)

// WithAPIBase sets the base URL of the GitHub API.
func WithAPIBase(base string) Option { return func(u *Updater) { u.apiBase = base } }

// WithHTTPClient sets the HTTP client for the release list and the downloads.
func WithHTTPClient(c *http.Client) Option { return func(u *Updater) { u.client = c } }

// WithPlatform sets the OS and the architecture of the release archive.
func WithPlatform(goos, goarch string) Option {
	return func(u *Updater) { u.goos, u.goarch = goos, goarch }
}

// WithExecutable sets the function that returns the path of the binary to replace. New reads
// that binary once, and the Updater takes it as the binary of the process start.
func WithExecutable(f func() (string, error)) Option { return func(u *Updater) { u.executable = f } }

// WithStateDir sets the directory of the daily state file and its lock.
func WithStateDir(dir string) Option { return func(u *Updater) { u.stateDir = dir } }

// WithNow sets the clock that decides the calendar day of the daily check.
func WithNow(now func() time.Time) Option { return func(u *Updater) { u.now = now } }

// New returns an Updater for the running version current.
func New(current string, opts ...Option) *Updater {
	u := &Updater{
		current: current,
		apiBase: DefaultAPIBase,
		client:  http.DefaultClient,
		goos:    runtime.GOOS,
		goarch:  runtime.GOARCH,
		now:     time.Now,
		geteuid: os.Geteuid,
		started: func() (string, os.FileInfo, error) { return startPath, startInfo, startErr },
	}
	for _, opt := range opts {
		opt(u)
	}
	if u.executable != nil {
		path, info, err := statExecutable(u.executable)
		u.started = func() (string, os.FileInfo, error) { return path, info, err }
	}
	return u
}

// replaced reports whether the file at path is no longer the file that started describes.
func replaced(path string, started os.FileInfo) bool {
	now, err := os.Stat(path)
	return err != nil || !os.SameFile(started, now)
}

// ownedByCaller reports whether the effective user of the process owns the binary and is not
// root. A root process, as from sudo, must not replace the version that the owner installed.
func (u *Updater) ownedByCaller(info os.FileInfo) bool {
	euid := u.geteuid()
	if euid == 0 {
		return false
	}
	st, ok := info.Sys().(*syscall.Stat_t)
	return ok && int(st.Uid) == euid
}

// accessWrite is W_OK of access(2), the same value on Linux and macOS.
const accessWrite = 0x2

// writable returns ErrInstall when the process cannot create a file in dir, for example on a
// read-only mount.
func writable(dir string) error {
	if err := syscall.Access(dir, accessWrite); err != nil {
		return fmt.Errorf("%w: %s is not writable: %w", ErrInstall, dir, err)
	}
	return nil
}

// latest returns the release that may replace the running binary.
func (u *Updater) latest(ctx context.Context, timeout time.Duration, allowPrerelease bool) (Release, bool, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	releases, err := ListReleases(ctx, u.apiBase, u.client, u.goos, u.goarch)
	if err != nil {
		return Release{}, false, err
	}
	release, ok := Select(u.current, releases, allowPrerelease)
	return release, ok, nil
}

func (u *Updater) install(ctx context.Context, timeout time.Duration, r Release, path string) error {
	name, err := ArchiveName(r.Version, u.goos, u.goarch)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	return Install(ctx, u.client, r, name, path)
}

// Upgrade installs the newest allowed release over the running binary.
//
// It waits for the lock of the directory of the binary, so one update at a time replaces the
// binary. When another update replaced the binary after this process started, Upgrade returns
// ErrBinaryReplaced and changes nothing. When the directory is not writable, Upgrade returns
// ErrInstall before the release list request.
func (u *Updater) Upgrade(ctx context.Context, allowPrerelease bool) (Result, error) {
	if IsDev(u.current) {
		return Result{}, ErrDevBuild
	}
	path, started, err := u.started()
	if err != nil {
		return Result{}, err
	}
	unlock, err := waitLockBinaryDir(ctx, filepath.Dir(path))
	if err != nil {
		return Result{}, err
	}
	defer unlock()
	if replaced(path, started) {
		return Result{}, ErrBinaryReplaced
	}
	if err = writable(filepath.Dir(path)); err != nil {
		return Result{}, err
	}

	release, ok, err := u.latest(ctx, UpgradeListTimeout, allowPrerelease)
	if err != nil {
		return Result{}, err
	}
	if !ok {
		return Result{From: u.current, To: u.current, Path: path}, nil
	}
	if err = u.install(ctx, UpgradeInstallTimeout, release, path); err != nil {
		return Result{}, err
	}
	return Result{From: u.current, To: release.Version, Upgraded: true, Path: path}, nil
}

// installWarning returns the stderr line of a failed daily install. It names argus upgrade only
// when a second attempt can succeed: a bad archive fails the same way again.
func installWarning(version string, err error) string {
	if errors.Is(err, ErrChecksum) || errors.Is(err, ErrBinaryNotInArchive) || errors.Is(err, ErrArchiveTooLarge) {
		return fmt.Sprintf("argus: cannot upgrade to %s: %v", version, err)
	}
	return fmt.Sprintf("argus: cannot upgrade to %s: %v; run argus upgrade", version, err)
}

// Daily runs the check of the first command of the local calendar day.
//
// It returns at once for a dev build, when the process runs as root or as a user that does not
// own the binary, when the directory of the binary is not writable, when another process holds
// the lock of the state directory or of the directory of the binary, when another update replaced
// the binary after this process started, or when the state file says the check already ran
// today. These checks send no request. It writes today to the state
// file before the release list request, so a failed check waits for the next day. A failed
// install writes one warning line to stderr, unless ctx ended. A successful install writes one
// line that names both versions.
func (u *Updater) Daily(ctx context.Context, stderr io.Writer) (Result, error) {
	if IsDev(u.current) || u.stateDir == "" {
		return Result{}, nil
	}
	path, started, err := u.started()
	if err != nil {
		return Result{}, err
	}
	if !u.ownedByCaller(started) || writable(filepath.Dir(path)) != nil {
		return Result{}, nil
	}
	unlockState, err := tryLock(u.stateDir)
	if err != nil || unlockState == nil {
		return Result{}, err
	}
	defer unlockState()
	unlockDir, err := tryLockBinaryDir(filepath.Dir(path))
	if err != nil || unlockDir == nil {
		return Result{}, err
	}
	defer unlockDir()
	if replaced(path, started) {
		return Result{}, nil
	}

	today := u.now().Local().Format(dayLayout)
	if readState(u.stateDir).LastCheck == today {
		return Result{}, nil
	}
	if err = writeState(u.stateDir, state{LastCheck: today}); err != nil {
		return Result{}, err
	}

	release, ok, err := u.latest(ctx, ListTimeout, false)
	if err != nil || !ok {
		return Result{}, err
	}
	if err = u.install(ctx, InstallTimeout, release, path); err != nil {
		if ctx.Err() == nil {
			_, _ = fmt.Fprintln(stderr, installWarning(release.Version, err))
		}
		return Result{}, err
	}
	_, _ = fmt.Fprintf(stderr, "argus: upgraded %s -> %s\n", u.current, release.Version)
	return Result{From: u.current, To: release.Version, Upgraded: true, Path: path}, nil
}
