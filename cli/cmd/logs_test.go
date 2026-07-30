package cmd

import (
	"archive/tar"
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/klauspost/compress/zstd"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func zstCompress(t *testing.T, data []byte) []byte {
	t.Helper()
	var buf bytes.Buffer
	zw, err := zstd.NewWriter(&buf)
	require.NoError(t, err)
	_, err = zw.Write(data)
	require.NoError(t, err)
	require.NoError(t, zw.Close())
	return buf.Bytes()
}

func TestExtractPlainZst_WritesDecompressedFile(t *testing.T) {
	dest := t.TempDir()
	content := []byte("2026-07-28 14:22:21 INFO some SCT runner log line\n")
	compressed := zstCompress(t, content)

	err := extractPlainZst("2026_07_28__14_22_21_539.chunk_01.sct-a3f4208c.log.zst", bytes.NewReader(compressed), dest)
	require.NoError(t, err)

	got, err := os.ReadFile(filepath.Join(dest, "2026_07_28__14_22_21_539.chunk_01.sct-a3f4208c.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractPlainZst_RejectsUnsafePath(t *testing.T) {
	dest := t.TempDir()

	for _, logName := range []string{"../../etc/evil.log.zst", "/etc/passwd.log.zst"} {
		compressed := zstCompress(t, []byte("data"))
		err := extractPlainZst(logName, bytes.NewReader(compressed), dest)
		require.Error(t, err, "logName=%q", logName)
		assert.Contains(t, err.Error(), "unsafe path")
	}
}

func TestExtractPlainZst_RejectsEmptyOrBareSuffixName(t *testing.T) {
	dest := t.TempDir()

	for _, logName := range []string{"", ".zst"} {
		compressed := zstCompress(t, []byte("data"))
		err := extractPlainZst(logName, bytes.NewReader(compressed), dest)
		require.Error(t, err, "logName=%q", logName)
		assert.Contains(t, err.Error(), "invalid")
	}
}

func TestExtractTarZst_ExtractsTarArchive(t *testing.T) {
	dest := t.TempDir()

	var tarBuf bytes.Buffer
	tw := tar.NewWriter(&tarBuf)
	content := []byte("hello from a tar archive\n")
	require.NoError(t, tw.WriteHeader(&tar.Header{
		Name: "schema.log",
		Mode: 0644,
		Size: int64(len(content)),
	}))
	_, err := tw.Write(content)
	require.NoError(t, err)
	require.NoError(t, tw.Close())

	compressed := zstCompress(t, tarBuf.Bytes())

	err = extractTarZst(bytes.NewReader(compressed), dest)
	require.NoError(t, err)

	got, err := os.ReadFile(filepath.Join(dest, "schema.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestIsTarZstName_ExactSuffixOnly(t *testing.T) {
	tests := []struct {
		logName string
		want    bool
	}{
		{"schema-logs-a3f4208c.tar.zst", true},
		{"schema-logs-a3f4208c.tar.zstd", true},
		{"2026_07_28__14_22_21_539.chunk_01.sct-a3f4208c.log.zst", false},
		// Contains ".tar." but does not end in a known tar-zst suffix — must
		// not be routed to extractTarZst, which is zstd-only.
		{"foo.tar.old.log.zst", false},
		{"foo.tar.gz", false},
	}
	for _, tc := range tests {
		assert.Equal(t, tc.want, isTarZstName(tc.logName), "logName=%q", tc.logName)
	}
}

func TestExtractTarZst_RejectsBarePlainLog(t *testing.T) {
	dest := t.TempDir()
	// A full 512-byte tar header block is required before the tar reader
	// evaluates its contents as a (bad) header rather than reporting a
	// truncated read.
	content := bytes.Repeat([]byte("plain log content, not a tar archive\n"), 20)
	compressed := zstCompress(t, content)

	err := extractTarZst(bytes.NewReader(compressed), dest)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid tar header")
}
