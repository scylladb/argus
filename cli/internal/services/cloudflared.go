package services

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/scylladb/argus/cli/internal/config"
)

const (
	cloudflaredBinary  = "cloudflared"
	cloudflaredBaseURL = "https://github.com/cloudflare/cloudflared/releases/latest/download"
	downloadTimeout    = 5 * time.Minute
)

// Sentinel errors returned by the services package.
var (
	// ErrUnsupportedPlatform is returned when the current OS/arch combination
	// has no known cloudflared release asset.
	ErrUnsupportedPlatform = errors.New("cloudflared: unsupported platform")

	// ErrCreatingCacheDir is returned when the cache directory for the managed
	// binary cannot be created.
	ErrCreatingCacheDir = errors.New("cloudflared: creating cache directory")

	// ErrBuildingDownloadRequest is returned when the HTTP request for the
	// cloudflared binary cannot be constructed.
	ErrBuildingDownloadRequest = errors.New("cloudflared: building download request")

	// ErrDownloading is returned when the HTTP transfer itself fails.
	ErrDownloading = errors.New("cloudflared: downloading")

	// ErrUnexpectedHTTPStatus is returned when the download server responds
	// with a non-200 status code.
	ErrUnexpectedHTTPStatus = errors.New("cloudflared: unexpected HTTP status")

	// ErrCreatingTempFile is returned when the temporary download file cannot
	// be created.
	ErrCreatingTempFile = errors.New("cloudflared: creating temp file")

	// ErrWritingBinary is returned when copying the download body to disk fails.
	ErrWritingBinary = errors.New("cloudflared: writing binary")

	// ErrClosingTempFile is returned when flushing/closing the temporary file
	// fails.
	ErrClosingTempFile = errors.New("cloudflared: closing temp file")

	// ErrSettingExecutableBit is returned when chmod on the downloaded binary
	// fails.
	ErrSettingExecutableBit = errors.New("cloudflared: setting executable bit")

	// ErrInstallingBinary is returned when the atomic rename into the final
	// cache path fails.
	ErrInstallingBinary = errors.New("cloudflared: installing binary")

	// ErrOpeningGzipStream is returned when the gzip layer of a .tgz asset
	// cannot be opened.
	ErrOpeningGzipStream = errors.New("cloudflared: opening gzip stream")

	// ErrReadingTarball is returned when iterating the tar entries fails.
	ErrReadingTarball = errors.New("cloudflared: reading tarball")

	// ErrBinaryNotInTarball is returned when the cloudflared binary entry is
	// not found inside the downloaded .tgz archive.
	ErrBinaryNotInTarball = errors.New("cloudflared: binary not found inside tarball")
)

// CloudflaredService manages the lifecycle of the cloudflared binary used for
// Cloudflare Access authentication.
type CloudflaredService struct {
	// binaryPath is the full path to the cloudflared binary that this service
	// manages (i.e. the one inside the XDG cache directory).
	binaryPath string

	// httpClient is used for the download; injectable for testing.
	httpClient *http.Client

	// urlOverridden, downloadURL, and isTarball let tests pin the asset URL
	// without going through platform detection.
	urlOverridden bool
	downloadURL   string
	isTarball     bool
}

// NewCloudflaredService constructs a CloudflaredService whose managed binary
// lives at $XDG_CACHE_HOME/argus-cli/cloudflared (or cloudflared.exe on
// Windows).
func NewCloudflaredService(opts ...CloudflaredOption) *CloudflaredService {
	name := cloudflaredBinary
	if runtime.GOOS == "windows" {
		name += ".exe"
	}

	s := &CloudflaredService{
		binaryPath: filepath.Join(config.CacheDir(), name),
		httpClient: &http.Client{Timeout: downloadTimeout},
	}

	for _, o := range opts {
		o(s)
	}

	return s
}

// CloudflaredOption is a functional option for [NewCloudflaredService].
type CloudflaredOption func(*CloudflaredService)

// WithHTTPClient overrides the HTTP client used for downloads.
// Primarily useful in tests to inject an [httptest.Server].
func WithHTTPClient(c *http.Client) CloudflaredOption {
	return func(s *CloudflaredService) { s.httpClient = c }
}

// WithBinaryPath overrides the path where the managed binary is stored.
// Primarily useful in tests to avoid writing into the real cache directory.
func WithBinaryPath(p string) CloudflaredOption {
	return func(s *CloudflaredService) { s.binaryPath = p }
}

// WithDownloadURL pins the download URL and tarball flag, bypassing the
// platform-detection logic in [AssetURL].  Primarily useful in tests.
func WithDownloadURL(url string, isTarball bool) CloudflaredOption {
	return func(s *CloudflaredService) {
		s.downloadURL = url
		s.isTarball = isTarball
		s.urlOverridden = true
	}
}

// BinaryPath returns the path to the managed cloudflared binary inside the
// cache directory.
func (s *CloudflaredService) BinaryPath() string {
	return s.binaryPath
}

func (s *CloudflaredService) Ensure(ctx context.Context) (string, error) {
	// Already on PATH?
	if p, err := exec.LookPath(cloudflaredBinary); err == nil {
		return p, nil
	}

	// Already cached?
	if _, err := os.Stat(s.binaryPath); err == nil {
		return s.binaryPath, nil
	}

	// Download.
	if err := s.download(ctx); err != nil {
		return "", err
	}

	return s.binaryPath, nil
}

func (s *CloudflaredService) download(ctx context.Context) error {
	var (
		url       string
		isTarball bool
		err       error
	)

	if s.urlOverridden {
		url, isTarball = s.downloadURL, s.isTarball
	} else {
		url, isTarball, err = AssetURL(runtime.GOOS, runtime.GOARCH)
		if err != nil {
			return err
		}
	}

	if err = os.MkdirAll(filepath.Dir(s.binaryPath), 0o700); err != nil {
		return fmt.Errorf("%w: %w", ErrCreatingCacheDir, err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrBuildingDownloadRequest, err)
	}

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrDownloading, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%w: %d from %s", ErrUnexpectedHTTPStatus, resp.StatusCode, url)
	}

	// Write to a temp file in the same directory first so we never leave a
	// partial binary at the final path if the download is interrupted.
	tmp, err := os.CreateTemp(filepath.Dir(s.binaryPath), ".cloudflared-download-*")
	if err != nil {
		return fmt.Errorf("%w: %w", ErrCreatingTempFile, err)
	}
	tmpName := tmp.Name()
	defer func() {
		tmp.Close()
		// Clean up temp file on any error path; ignore removal errors.
		os.Remove(tmpName)
	}()

	var src io.Reader = resp.Body

	if isTarball {
		// macOS assets are .tgz archives containing the bare binary.
		src, err = extractFromTarball(resp.Body)
		if err != nil {
			return err
		}
	}

	if _, err = io.Copy(tmp, src); err != nil {
		return fmt.Errorf("%w: %w", ErrWritingBinary, err)
	}

	if err = tmp.Close(); err != nil {
		return fmt.Errorf("%w: %w", ErrClosingTempFile, err)
	}

	if err = os.Chmod(tmpName, 0o755); err != nil {
		return fmt.Errorf("%w: %w", ErrSettingExecutableBit, err)
	}

	if err = os.Rename(tmpName, s.binaryPath); err != nil {
		return fmt.Errorf("%w: %w", ErrInstallingBinary, err)
	}

	return nil
}

// extractFromTarball returns a reader positioned at the cloudflared binary
// inside a .tgz archive stream.
func extractFromTarball(r io.Reader) (io.Reader, error) {
	gz, err := gzip.NewReader(r)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrOpeningGzipStream, err)
	}

	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("%w: %w", ErrReadingTarball, err)
		}

		if filepath.Base(hdr.Name) == cloudflaredBinary {
			return tr, nil
		}
	}

	return nil, ErrBinaryNotInTarball
}

// AssetURL returns the download URL for the cloudflared binary on the given
// OS/arch and whether the asset is a tarball (.tgz) that needs extraction.
//
// Supported combinations mirror the official release matrix:
//
//	linux:   amd64, arm64, arm, 386
//	darwin:  amd64, arm64  (.tgz)
//	windows: amd64, 386    (.exe)
func AssetURL(goos, goarch string) (url string, isTarball bool, err error) {
	// Maps Go arch names to the names used in cloudflared release assets.
	archAlias := map[string]string{
		"amd64": "amd64",
		"arm64": "arm64",
		"arm":   "arm",
		"386":   "386",
	}

	cfArch, ok := archAlias[goarch]
	if !ok {
		return "", false, fmt.Errorf("%w: %s/%s", ErrUnsupportedPlatform, goos, goarch)
	}

	switch goos {
	case "linux":
		// Bare binary: cloudflared-linux-{arch}
		url = fmt.Sprintf("%s/cloudflared-linux-%s", cloudflaredBaseURL, cfArch)
	case "darwin":
		// Tarball: cloudflared-darwin-{arch}.tgz
		url = fmt.Sprintf("%s/cloudflared-darwin-%s.tgz", cloudflaredBaseURL, cfArch)
		isTarball = true
	case "windows":
		if goarch == "arm" || goarch == "arm64" {
			return "", false, fmt.Errorf("%w: %s/%s", ErrUnsupportedPlatform, goos, goarch)
		}
		// Executable: cloudflared-windows-{arch}.exe
		url = fmt.Sprintf("%s/cloudflared-windows-%s.exe", cloudflaredBaseURL, cfArch)
	default:
		return "", false, fmt.Errorf("%w: %s/%s", ErrUnsupportedPlatform, goos, goarch)
	}

	return url, isTarball, nil
}
