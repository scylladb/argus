package services_test

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/services"
)

// ---- assetURL tests --------------------------------------------------------

func TestAssetURL_Linux(t *testing.T) {
	cases := []struct {
		arch        string
		wantSuffix  string
		wantTarball bool
	}{
		{"amd64", "cloudflared-linux-amd64", false},
		{"arm64", "cloudflared-linux-arm64", false},
	}
	for _, tc := range cases {
		t.Run(tc.arch, func(t *testing.T) {
			url, tarball, err := services.AssetURL("linux", tc.arch)
			require.NoError(t, err)
			assert.Contains(t, url, tc.wantSuffix)
			assert.Equal(t, tc.wantTarball, tarball)
		})
	}
}

func TestAssetURL_Darwin(t *testing.T) {
	cases := []struct {
		arch string
	}{
		{"amd64"},
		{"arm64"},
	}
	for _, tc := range cases {
		t.Run(tc.arch, func(t *testing.T) {
			url, tarball, err := services.AssetURL("darwin", tc.arch)
			require.NoError(t, err)
			assert.Contains(t, url, "darwin-"+tc.arch+".tgz")
			assert.True(t, tarball, "darwin assets should be tarballs")
		})
	}
}

func TestAssetURL_Windows(t *testing.T) {
	cases := []struct {
		arch string
	}{
		{"amd64"},
		{"386"},
	}
	for _, tc := range cases {
		t.Run(tc.arch, func(t *testing.T) {
			url, tarball, err := services.AssetURL("windows", tc.arch)
			require.NoError(t, err)
			assert.Contains(t, url, "windows-"+tc.arch+".exe")
			assert.False(t, tarball)
		})
	}
}

func TestAssetURL_Unsupported(t *testing.T) {
	cases := []struct{ goos, goarch string }{
		{"freebsd", "amd64"},
		{"linux", "mips"},
		{"windows", "arm64"},
		{"windows", "arm"},
		{"plan9", "amd64"},
	}
	for _, tc := range cases {
		t.Run(tc.goos+"/"+tc.goarch, func(t *testing.T) {
			_, _, err := services.AssetURL(tc.goos, tc.goarch)
			require.Error(t, err)
			assert.ErrorIs(t, err, services.ErrUnsupportedPlatform)
		})
	}
}

// ---- Ensure tests ----------------------------------------------------------

// TestEnsure_PathHit verifies that when cloudflared is already on PATH,
// Ensure returns that path without downloading anything.
func TestEnsure_PathHit(t *testing.T) {
	// Create a fake executable named "cloudflared" in a temp dir and put it on PATH.
	dir := t.TempDir()
	fakeBin := filepath.Join(dir, "cloudflared")
	require.NoError(t, os.WriteFile(fakeBin, []byte("#!/bin/sh\n"), 0o755))
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(filepath.Join(t.TempDir(), "cloudflared")),
	)

	got, err := svc.Ensure(t.Context())
	require.NoError(t, err)
	assert.Equal(t, fakeBin, got)
}

// TestEnsure_CacheHit verifies that when the managed binary already exists in
// the cache directory, Ensure returns it without downloading.
func TestEnsure_CacheHit(t *testing.T) {
	cacheDir := t.TempDir()
	cachedBin := filepath.Join(cacheDir, "cloudflared")
	require.NoError(t, os.WriteFile(cachedBin, []byte("fake"), 0o755))

	// Use an unreachable server to prove nothing is downloaded.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("download should not have been attempted")
	}))
	t.Cleanup(srv.Close)

	// Remove cloudflared from PATH so the PATH check falls through.
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(cachedBin),
		services.WithHTTPClient(srv.Client()),
	)

	got, err := svc.Ensure(t.Context())
	require.NoError(t, err)
	assert.Equal(t, cachedBin, got)
}

// TestEnsure_Download_BareBinary verifies the happy-path download of a bare
// binary (the Linux case).
func TestEnsure_Download_BareBinary(t *testing.T) {
	const fakeContent = "fake-cloudflared-binary"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(fakeContent))
	}))
	t.Cleanup(srv.Close)

	destDir := t.TempDir()
	destBin := filepath.Join(destDir, "cloudflared")

	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-linux-amd64", false),
	)

	got, err := svc.Ensure(t.Context())
	require.NoError(t, err)
	assert.Equal(t, destBin, got)

	data, err := os.ReadFile(destBin)
	require.NoError(t, err)
	assert.Equal(t, fakeContent, string(data))

	info, err := os.Stat(destBin)
	require.NoError(t, err)
	assert.True(t, info.Mode()&0o111 != 0, "binary should be executable")
}

// TestEnsure_Download_Tarball verifies extraction of the binary from a .tgz
// archive (the macOS case).
func TestEnsure_Download_Tarball(t *testing.T) {
	const fakeContent = "fake-cloudflared-inside-tar"

	tarball := makeTarball(t, "cloudflared", []byte(fakeContent))

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(tarball)
	}))
	t.Cleanup(srv.Close)

	destDir := t.TempDir()
	destBin := filepath.Join(destDir, "cloudflared")

	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-darwin-arm64.tgz", true),
	)

	got, err := svc.Ensure(t.Context())
	require.NoError(t, err)
	assert.Equal(t, destBin, got)

	data, err := os.ReadFile(destBin)
	require.NoError(t, err)
	assert.Equal(t, fakeContent, string(data))
}

// TestEnsure_Download_HTTPError verifies that a non-200 response is surfaced
// as an error.
func TestEnsure_Download_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-linux-amd64", false),
	)

	_, err := svc.Ensure(t.Context())
	require.Error(t, err)
	assert.ErrorContains(t, err, "404")
}

// TestEnsure_Download_Cancelled verifies that context cancellation aborts the
// download and surfaces the context error.
func TestEnsure_Download_Cancelled(t *testing.T) {
	ready := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(ready)
		// Block until the client disconnects.
		<-r.Context().Done()
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-linux-amd64", false),
	)

	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()

	errc := make(chan error, 1)
	go func() {
		_, err := svc.Ensure(ctx)
		errc <- err
	}()

	<-ready  // wait for the server to have received the request
	cancel() // abort the in-flight download

	err := <-errc
	require.Error(t, err)
	assert.ErrorIs(t, err, context.Canceled)
}

// ---- helpers ---------------------------------------------------------------

// makeTarball creates an in-memory .tgz archive containing a single file with
// the given name and content.
func makeTarball(t *testing.T, name string, content []byte) []byte {
	t.Helper()
	var buf bytes.Buffer

	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)

	hdr := &tar.Header{
		Name: name,
		Mode: 0o755,
		Size: int64(len(content)),
	}
	require.NoError(t, tw.WriteHeader(hdr))
	_, err := tw.Write(content)
	require.NoError(t, err)
	require.NoError(t, tw.Close())
	require.NoError(t, gz.Close())

	return buf.Bytes()
}

// --------------------------------------------------------------------------
// Additional AssetURL cases
// --------------------------------------------------------------------------

func TestAssetURL_Linux_Arm_And_386(t *testing.T) {
	t.Parallel()

	cases := []struct {
		arch       string
		wantSuffix string
	}{
		{"arm", "cloudflared-linux-arm"},
		{"386", "cloudflared-linux-386"},
	}

	for _, tc := range cases {
		t.Run(tc.arch, func(t *testing.T) {
			t.Parallel()
			url, tarball, err := services.AssetURL("linux", tc.arch)
			require.NoError(t, err)
			assert.Contains(t, url, tc.wantSuffix)
			assert.False(t, tarball, "linux assets are not tarballs")
		})
	}
}

// --------------------------------------------------------------------------
// ErrUnexpectedHTTPStatus via errors.Is
// --------------------------------------------------------------------------

func TestEnsure_Download_HTTPError_IsErrUnexpectedHTTPStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-linux-amd64", false),
	)

	_, err := svc.Ensure(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrUnexpectedHTTPStatus,
		"a non-200 response should wrap ErrUnexpectedHTTPStatus")
}

// --------------------------------------------------------------------------
// Tarball error cases
// --------------------------------------------------------------------------

func TestEnsure_Download_CorruptedGzip(t *testing.T) {
	// Serve data that is not a valid gzip stream to trigger ErrOpeningGzipStream.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("this is not gzip data at all"))
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-darwin-arm64.tgz", true),
	)

	_, err := svc.Ensure(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrOpeningGzipStream)
}

func TestEnsure_Download_CorruptedTar(t *testing.T) {
	// Build a valid gzip wrapper around corrupted tar data to trigger ErrReadingTarball.
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	_, _ = gz.Write([]byte("this is not valid tar data"))
	_ = gz.Close()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(buf.Bytes())
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-darwin-arm64.tgz", true),
	)

	_, err := svc.Ensure(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrReadingTarball)
}

func TestEnsure_Download_BinaryNotInTarball(t *testing.T) {
	// Tarball that contains a file with a different name.
	tarball := makeTarball(t, "not-cloudflared", []byte("some content"))

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(tarball)
	}))
	t.Cleanup(srv.Close)

	destBin := filepath.Join(t.TempDir(), "cloudflared")
	t.Setenv("PATH", "")

	svc := services.NewCloudflaredService(
		services.WithBinaryPath(destBin),
		services.WithHTTPClient(srv.Client()),
		services.WithDownloadURL(srv.URL+"/cloudflared-darwin-arm64.tgz", true),
	)

	_, err := svc.Ensure(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrBinaryNotInTarball)
}

// --------------------------------------------------------------------------
// BinaryPath
// --------------------------------------------------------------------------

func TestBinaryPath_ReturnsConfiguredPath(t *testing.T) {
	t.Parallel()

	customPath := filepath.Join(t.TempDir(), "my-cloudflared")
	svc := services.NewCloudflaredService(
		services.WithBinaryPath(customPath),
	)
	assert.Equal(t, customPath, svc.BinaryPath())
}
