package selfupdate_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

// fakeGitHub serves one CLI release, 0.6.0 for linux/amd64, and counts the release list calls.
type fakeGitHub struct {
	srv       *httptest.Server
	listCalls atomic.Int32
	status    int
	// badSum makes the checksum file name a sum that does not match the archive.
	badSum bool
	// onArchive runs when the archive download starts. The download then waits until the
	// client cancels the request.
	onArchive func()
	// archiveStatus, when set, is the status of the archive download.
	archiveStatus int
}

func newFakeGitHub(t *testing.T) *fakeGitHub {
	t.Helper()
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GH_TOKEN", "")
	f := &fakeGitHub{status: http.StatusOK}
	archive := tarball(t, map[string]string{"argus": "new"})
	mux := http.NewServeMux()
	mux.HandleFunc("/repos/scylladb/argus/releases", func(w http.ResponseWriter, _ *http.Request) {
		f.listCalls.Add(1)
		if f.status != http.StatusOK {
			w.WriteHeader(f.status)
			return
		}
		body, _ := json.Marshal([]map[string]any{{
			"tag_name": "cli/v0.6.0", "draft": false, "prerelease": false,
			"assets": []map[string]string{
				{"name": archiveName, "browser_download_url": f.srv.URL + "/archive"},
				{"name": "argus_0.6.0_checksums.txt", "browser_download_url": f.srv.URL + "/sums"},
			},
		}})
		_, _ = w.Write(body)
	})
	mux.HandleFunc("/archive", func(w http.ResponseWriter, r *http.Request) {
		if f.archiveStatus != 0 {
			w.WriteHeader(f.archiveStatus)
			return
		}
		if f.onArchive != nil {
			// Answer only after the client gave up, so the install sees the canceled context.
			f.onArchive()
			<-r.Context().Done()
			return
		}
		_, _ = w.Write(archive)
	})
	mux.HandleFunc("/sums", func(w http.ResponseWriter, _ *http.Request) {
		want := sum(archive)
		if f.badSum {
			want = sum([]byte("other"))
		}
		_, _ = w.Write([]byte(want + "  " + archiveName + "\n"))
	})
	f.srv = httptest.NewServer(mux)
	t.Cleanup(f.srv.Close)
	return f
}

type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

func newUpdater(f *fakeGitHub, current, target, stateDir string, c *clock, opts ...selfupdate.Option) *selfupdate.Updater {
	return selfupdate.New(current, append([]selfupdate.Option{
		selfupdate.WithAPIBase(f.srv.URL),
		selfupdate.WithHTTPClient(f.srv.Client()),
		selfupdate.WithPlatform("linux", "amd64"),
		selfupdate.WithExecutable(func() (string, error) { return target, nil }),
		selfupdate.WithStateDir(stateDir),
		selfupdate.WithNow(c.Now),
	}, opts...)...)
}

// readOnlyDir makes the directory of target read-only for the test.
func readOnlyDir(t *testing.T, target string) {
	t.Helper()
	if os.Geteuid() == 0 {
		t.Skip("root writes to a read-only directory")
	}
	dir := filepath.Dir(target)
	require.NoError(t, os.Chmod(dir, 0o555))
	t.Cleanup(func() { _ = os.Chmod(dir, 0o755) })
}

func TestDaily_InstallsOnceADay(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	c := &clock{now: time.Date(2026, 11, 12, 9, 0, 0, 0, time.Local)}
	var stderr bytes.Buffer

	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), c).Daily(context.Background(), &stderr)
	require.NoError(t, err)

	assert.Equal(t, selfupdate.Result{From: "0.5.0", To: "0.6.0", Upgraded: true, Path: target}, res)
	assert.Equal(t, "argus: upgraded 0.5.0 -> 0.6.0\n", stderr.String())
	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "new", string(got))
}

func TestDaily_SecondRunOnTheSameDaySendsNoRequest(t *testing.T) {
	f := newFakeGitHub(t)
	stateDir := t.TempDir()
	c := &clock{now: time.Date(2026, 11, 12, 9, 0, 0, 0, time.Local)}

	_, err := newUpdater(f, "0.6.0", oldBinary(t), stateDir, c).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)
	c.now = c.now.Add(10 * time.Hour)
	_, err = newUpdater(f, "0.6.0", oldBinary(t), stateDir, c).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)
	assert.Equal(t, int32(1), f.listCalls.Load())

	c.now = c.now.Add(5 * time.Hour)
	_, err = newUpdater(f, "0.6.0", oldBinary(t), stateDir, c).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)
	assert.Equal(t, int32(2), f.listCalls.Load())
}

func TestDaily_FailedListStillWritesTheDate(t *testing.T) {
	f := newFakeGitHub(t)
	f.status = http.StatusForbidden
	stateDir := t.TempDir()
	c := &clock{now: time.Date(2026, 11, 12, 9, 0, 0, 0, time.Local)}
	var stderr bytes.Buffer

	_, err := newUpdater(f, "0.5.0", oldBinary(t), stateDir, c).Daily(context.Background(), &stderr)
	require.ErrorIs(t, err, selfupdate.ErrReleaseList)
	_, err = newUpdater(f, "0.5.0", oldBinary(t), stateDir, c).Daily(context.Background(), &stderr)
	require.NoError(t, err)

	assert.Equal(t, int32(1), f.listCalls.Load())
	assert.Empty(t, stderr.String())
}

func TestDaily_HeldLockSkipsTheCheck(t *testing.T) {
	f := newFakeGitHub(t)
	stateDir := t.TempDir()
	lock, err := os.OpenFile(filepath.Join(stateDir, "upgrade.lock"), os.O_CREATE|os.O_RDWR, 0o600)
	require.NoError(t, err)
	t.Cleanup(func() { _ = lock.Close() })
	require.NoError(t, syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB))

	res, err := newUpdater(f, "0.5.0", oldBinary(t), stateDir, &clock{now: time.Now()}).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)
	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestDaily_CorruptStateCountsAsNoCheck(t *testing.T) {
	f := newFakeGitHub(t)
	stateDir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(stateDir, "upgrade.json"), []byte("{not json"), 0o600))

	_, err := newUpdater(f, "0.6.0", oldBinary(t), stateDir, &clock{now: time.Now()}).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)
	assert.Equal(t, int32(1), f.listCalls.Load())
}

func TestDaily_FailedInstallWarnsOnce(t *testing.T) {
	f := newFakeGitHub(t)
	f.archiveStatus = http.StatusBadGateway
	var stderr bytes.Buffer

	_, err := newUpdater(f, "0.5.0", oldBinary(t), t.TempDir(), &clock{now: time.Now()}).Daily(context.Background(), &stderr)
	require.ErrorIs(t, err, selfupdate.ErrDownload)
	assert.Contains(t, stderr.String(), "argus: cannot upgrade to 0.6.0: ")
	assert.Contains(t, stderr.String(), "; run argus upgrade\n")
}

func TestDaily_RootSkipsTheCheck(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)

	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}, selfupdate.WithEUID(0)).
		Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)

	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestDaily_UserThatDoesNotOwnTheBinarySkipsTheCheck(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)

	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}, selfupdate.WithEUID(os.Geteuid()+1)).
		Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)

	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestDaily_ReadOnlyDirectorySkipsTheCheck(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	readOnlyDir(t, target)
	var stderr bytes.Buffer

	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Daily(context.Background(), &stderr)
	require.NoError(t, err)

	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
	assert.Empty(t, stderr.String())
}

func TestUpgrade_ReadOnlyDirectoryFailsBeforeTheList(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	readOnlyDir(t, target)

	_, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Upgrade(context.Background(), false)
	require.ErrorIs(t, err, selfupdate.ErrInstall)
	require.ErrorIs(t, err, fs.ErrPermission)

	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestUpgrade_DevBuild(t *testing.T) {
	f := newFakeGitHub(t)

	_, err := newUpdater(f, "dev", oldBinary(t), t.TempDir(), &clock{now: time.Now()}).Upgrade(context.Background(), false)
	require.ErrorIs(t, err, selfupdate.ErrDevBuild)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestUpgrade_UpToDate(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)

	res, err := newUpdater(f, "0.6.0", target, t.TempDir(), &clock{now: time.Now()}).Upgrade(context.Background(), false)
	require.NoError(t, err)
	assert.Equal(t, selfupdate.Result{From: "0.6.0", To: "0.6.0", Upgraded: false, Path: target}, res)
	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "old", string(got))
}

func TestDaily_BadChecksumWarnsWithoutTheUpgradeHint(t *testing.T) {
	f := newFakeGitHub(t)
	f.badSum = true
	var stderr bytes.Buffer

	_, err := newUpdater(f, "0.5.0", oldBinary(t), t.TempDir(), &clock{now: time.Now()}).Daily(context.Background(), &stderr)
	require.ErrorIs(t, err, selfupdate.ErrChecksum)

	assert.Contains(t, stderr.String(), "argus: cannot upgrade to 0.6.0: ")
	assert.NotContains(t, stderr.String(), "run argus upgrade")
}

// lockDir holds the flock of dir, as another update of a binary in dir does.
func lockDir(t *testing.T, dir string) func() {
	t.Helper()
	f, err := os.Open(dir)
	require.NoError(t, err)
	require.NoError(t, syscall.Flock(int(f.Fd()), syscall.LOCK_EX))
	var once sync.Once
	release := func() {
		once.Do(func() {
			_ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN)
			_ = f.Close()
		})
	}
	t.Cleanup(release)
	return release
}

// replaceFile renames a new file over path, as another update does.
func replaceFile(t *testing.T, path string) {
	t.Helper()
	other := path + ".other"
	require.NoError(t, os.WriteFile(other, []byte("other"), 0o755))
	require.NoError(t, os.Rename(other, path))
}

func TestUpgrade_StopsWhenTheBinaryWasReplaced(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	u := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()})
	replaceFile(t, target)

	_, err := u.Upgrade(context.Background(), false)
	require.ErrorIs(t, err, selfupdate.ErrBinaryReplaced)

	assert.Equal(t, int32(0), f.listCalls.Load())
	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "other", string(got))
}

func TestDaily_SkipsWhenTheBinaryWasReplaced(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	u := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()})
	replaceFile(t, target)

	res, err := u.Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)

	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestUpgrade_WaitsForTheLockOfTheBinaryDirectory(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	release := lockDir(t, filepath.Dir(target))
	const hold = 300 * time.Millisecond
	time.AfterFunc(hold, release)

	start := time.Now()
	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Upgrade(context.Background(), false)
	require.NoError(t, err)

	assert.GreaterOrEqual(t, time.Since(start), hold)
	assert.True(t, res.Upgraded)
}

func TestUpgrade_StopsWaitingForTheLockWhenTheContextEnds(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	lockDir(t, filepath.Dir(target))
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()

	_, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Upgrade(ctx, false)
	require.ErrorIs(t, err, selfupdate.ErrInstall)
	require.ErrorIs(t, err, context.DeadlineExceeded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestDaily_HeldBinaryDirectoryLockSkipsTheCheck(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	lockDir(t, filepath.Dir(target))

	res, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Daily(context.Background(), &bytes.Buffer{})
	require.NoError(t, err)

	assert.False(t, res.Upgraded)
	assert.Equal(t, int32(0), f.listCalls.Load())
}

func TestDaily_CanceledInstallPrintsNoWarning(t *testing.T) {
	f := newFakeGitHub(t)
	target := oldBinary(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	f.onArchive = cancel
	var stderr bytes.Buffer

	_, err := newUpdater(f, "0.5.0", target, t.TempDir(), &clock{now: time.Now()}).Daily(ctx, &stderr)
	require.ErrorIs(t, err, context.Canceled)

	assert.Empty(t, stderr.String())
	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "old", string(got))
}
