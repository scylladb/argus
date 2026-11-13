package selfupdate_test

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/scylladb/argus/cli/internal/selfupdate"
)

const archiveName = "argus_0.6.0_linux_amd64.tar.gz"

func tarball(t *testing.T, files map[string]string) []byte {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for name, body := range files {
		require.NoError(t, tw.WriteHeader(&tar.Header{Name: name, Mode: 0o755, Size: int64(len(body)), Typeflag: tar.TypeReg}))
		_, err := tw.Write([]byte(body))
		require.NoError(t, err)
	}
	require.NoError(t, tw.Close())
	require.NoError(t, gz.Close())
	return buf.Bytes()
}

func sum(b []byte) string {
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

// assetServer serves an archive and a checksum file, and returns the release that points to them.
func assetServer(t *testing.T, archive []byte, checksums string) selfupdate.Release {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/archive", func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write(archive) })
	mux.HandleFunc("/sums", func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(checksums)) })
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return selfupdate.Release{Version: "0.6.0", ArchiveURL: srv.URL + "/archive", ChecksumURL: srv.URL + "/sums"}
}

func oldBinary(t *testing.T) string {
	t.Helper()
	target := filepath.Join(t.TempDir(), "argus")
	require.NoError(t, os.WriteFile(target, []byte("old"), 0o750))
	return target
}

func dirEntries(t *testing.T, dir string) []string {
	t.Helper()
	entries, err := os.ReadDir(dir)
	require.NoError(t, err)
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		names = append(names, e.Name())
	}
	return names
}

func TestInstall_ReplacesTheBinaryAndKeepsItsMode(t *testing.T) {
	archive := tarball(t, map[string]string{"LICENSE": "license", "argus": "new"})
	release := assetServer(t, archive, "deadbeef  other.tar.gz\n"+sum(archive)+"  "+archiveName+"\n")
	target := oldBinary(t)

	require.NoError(t, selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target))

	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "new", string(got))
	info, err := os.Stat(target)
	require.NoError(t, err)
	assert.Equal(t, fs.FileMode(0o750), info.Mode().Perm())
	assert.Equal(t, []string{"argus"}, dirEntries(t, filepath.Dir(target)))
}

func TestInstall_WrongChecksumLeavesTheBinary(t *testing.T) {
	archive := tarball(t, map[string]string{"argus": "new"})
	release := assetServer(t, archive, sum([]byte("other"))+"  "+archiveName+"\n")
	target := oldBinary(t)

	err := selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target)
	require.ErrorIs(t, err, selfupdate.ErrChecksum)

	got, readErr := os.ReadFile(target)
	require.NoError(t, readErr)
	assert.Equal(t, "old", string(got))
	assert.Equal(t, []string{"argus"}, dirEntries(t, filepath.Dir(target)))
}

func TestInstall_MissingChecksumLine(t *testing.T) {
	archive := tarball(t, map[string]string{"argus": "new"})
	release := assetServer(t, archive, sum(archive)+"  argus_0.6.0_macOS_arm64.tar.gz\n")

	err := selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, oldBinary(t))
	require.ErrorIs(t, err, selfupdate.ErrChecksum)
}

func TestInstall_ArchiveWithoutBinary(t *testing.T) {
	archive := tarball(t, map[string]string{"README.md": "readme"})
	release := assetServer(t, archive, sum(archive)+"  "+archiveName+"\n")
	target := oldBinary(t)

	err := selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target)
	require.ErrorIs(t, err, selfupdate.ErrBinaryNotInArchive)
	assert.Equal(t, []string{"argus"}, dirEntries(t, filepath.Dir(target)))
}

func TestInstall_ReadOnlyDirectory(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root writes to a read-only directory")
	}
	archive := tarball(t, map[string]string{"argus": "new"})
	release := assetServer(t, archive, sum(archive)+"  "+archiveName+"\n")
	target := oldBinary(t)
	dir := filepath.Dir(target)
	require.NoError(t, os.Chmod(dir, 0o555))
	t.Cleanup(func() { _ = os.Chmod(dir, 0o755) })

	err := selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target)
	require.ErrorIs(t, err, fs.ErrPermission)
}

func TestInstall_ChecksumLineInBinaryMode(t *testing.T) {
	archive := tarball(t, map[string]string{"argus": "new"})
	release := assetServer(t, archive, sum(archive)+" *"+archiveName+"\n")
	target := oldBinary(t)

	require.NoError(t, selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target))
	got, err := os.ReadFile(target)
	require.NoError(t, err)
	assert.Equal(t, "new", string(got))
}

func TestInstall_RefusesAnOversizedBinary(t *testing.T) {
	// The header claims 300 MiB. Install must refuse it before it reads the body.
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	require.NoError(t, tw.WriteHeader(&tar.Header{Name: "argus", Mode: 0o755, Size: 300 << 20, Typeflag: tar.TypeReg}))
	_, err := tw.Write([]byte("partial"))
	require.NoError(t, err)
	require.NoError(t, gz.Close())
	archive := buf.Bytes()
	release := assetServer(t, archive, sum(archive)+"  "+archiveName+"\n")
	target := oldBinary(t)

	err = selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target)
	require.ErrorIs(t, err, selfupdate.ErrArchiveTooLarge)
	assert.Equal(t, []string{"argus"}, dirEntries(t, filepath.Dir(target)))
}

func TestInstall_RefusesAnOversizedArchive(t *testing.T) {
	selfupdate.SetMaxArchiveBytes(t, 1024)
	// The binary fits the limit, but the README before it does not.
	noise := make([]byte, 8192)
	_, err := rand.Read(noise)
	require.NoError(t, err)
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for _, f := range []struct {
		name string
		body []byte
	}{{"README.md", noise}, {"argus", []byte("new")}} {
		require.NoError(t, tw.WriteHeader(&tar.Header{Name: f.name, Mode: 0o755, Size: int64(len(f.body)), Typeflag: tar.TypeReg}))
		_, err = tw.Write(f.body)
		require.NoError(t, err)
	}
	require.NoError(t, tw.Close())
	require.NoError(t, gz.Close())
	archive := buf.Bytes()
	release := assetServer(t, archive, sum(archive)+"  "+archiveName+"\n")
	target := oldBinary(t)

	err = selfupdate.Install(context.Background(), http.DefaultClient, release, archiveName, target)
	require.ErrorIs(t, err, selfupdate.ErrArchiveTooLarge)
	assert.Equal(t, []string{"argus"}, dirEntries(t, filepath.Dir(target)))
}
