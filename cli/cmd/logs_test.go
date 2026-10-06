package cmd

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"encoding/binary"
	"errors"
	"io"
	"os"
	"path/filepath"
	"testing"

	"github.com/klauspost/compress/zstd"
	"github.com/scylladb/argus/cli/internal/api"
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

// extractBody handles body as the download command does for logName.
func extractBody(logName string, body []byte, dest string) error {
	lb, err := openLogBody(logName, bufio.NewReader(bytes.NewReader(body)))
	if err != nil {
		return err
	}
	defer lb.close()
	return lb.extract(logName, dest)
}

func TestExtractBody_ZstWritesDecompressedFile(t *testing.T) {
	dest := t.TempDir()
	content := []byte("2026-07-28 14:22:21 INFO some SCT runner log line\n")
	compressed := zstCompress(t, content)

	err := extractBody("2026_07_28__14_22_21_539.chunk_01.sct-a3f4208c.log.zst", compressed, dest)
	require.NoError(t, err)

	got, err := os.ReadFile(filepath.Join(dest, "2026_07_28__14_22_21_539.chunk_01.sct-a3f4208c.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_ZstRejectsUnsafePath(t *testing.T) {
	dest := t.TempDir()

	for _, logName := range []string{"../../etc/evil.log.zst", "/etc/passwd.log.zst"} {
		compressed := zstCompress(t, []byte("data"))
		err := extractBody(logName, compressed, dest)
		require.Error(t, err, "logName=%q", logName)
		assert.Contains(t, err.Error(), "unsafe path")
	}
}

func TestExtractBody_ZstRejectsEmptyOrBareSuffixName(t *testing.T) {
	dest := t.TempDir()

	for _, logName := range []string{"", ".zst"} {
		compressed := zstCompress(t, []byte("data"))
		err := extractBody(logName, compressed, dest)
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

func gzCompress(t *testing.T, data []byte) []byte {
	t.Helper()
	var buf bytes.Buffer
	gw := gzip.NewWriter(&buf)
	_, err := gw.Write(data)
	require.NoError(t, err)
	require.NoError(t, gw.Close())
	return buf.Bytes()
}

func tarArchive(t *testing.T, name string, content []byte) []byte {
	t.Helper()
	var buf bytes.Buffer
	tw := tar.NewWriter(&buf)
	require.NoError(t, tw.WriteHeader(&tar.Header{Name: name, Mode: 0644, Size: int64(len(content))}))
	_, err := tw.Write(content)
	require.NoError(t, err)
	require.NoError(t, tw.Close())
	return buf.Bytes()
}

func TestExtractBody_TarGzExtractsTarArchive(t *testing.T) {
	dest := t.TempDir()
	content := []byte("hello from a tar.gz archive\n")
	compressed := gzCompress(t, tarArchive(t, "schema.log", content))

	require.NoError(t, extractBody("schema-logs.tar.gz", compressed, dest))

	got, err := os.ReadFile(filepath.Join(dest, "schema.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_TarGzRejectsUnsafePath(t *testing.T) {
	dest := t.TempDir()
	compressed := gzCompress(t, tarArchive(t, "../evil.log", []byte("data")))

	err := extractBody("schema-logs.tar.gz", compressed, dest)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unsafe path")
}

func TestExtractBody_TarGzRejectsNonGzipInput(t *testing.T) {
	err := extractBody("schema-logs.tar.gz", []byte("not gzip data"), t.TempDir())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "gzip")
}

func TestExtractBody_GzWritesDecompressedFile(t *testing.T) {
	dest := t.TempDir()
	content := []byte("a gzip-compressed log line\n")

	err := extractBody("node-1.log.gz", gzCompress(t, content), dest)
	require.NoError(t, err)

	got, err := os.ReadFile(filepath.Join(dest, "node-1.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_GzRejectsUnsafePath(t *testing.T) {
	err := extractBody("../../evil.log.gz", gzCompress(t, []byte("data")), t.TempDir())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unsafe path")
}

func TestExtractBody_RawWritesUnknownFormatUnchanged(t *testing.T) {
	dest := t.TempDir()
	content := []byte("not compressed, not an archive\n")

	require.NoError(t, extractBody("events.log", content, dest))

	got, err := os.ReadFile(filepath.Join(dest, "events.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_RawRejectsUnsafePath(t *testing.T) {
	dest := t.TempDir()

	for _, logName := range []string{"../../etc/evil.log", "/etc/passwd"} {
		err := extractBody(logName, []byte("data"), dest)
		require.Error(t, err, "logName=%q", logName)
		assert.Contains(t, err.Error(), "unsafe path")
	}
}

// withSkippableFrame puts a zstd skippable frame with magic 0x184D2A5x before
// the zstd stream body.
func withSkippableFrame(body []byte) []byte {
	payload := []byte("pzstd")
	frame := make([]byte, 8, 8+len(payload)+len(body))
	binary.LittleEndian.PutUint32(frame[:4], 0x184D2A50)
	binary.LittleEndian.PutUint32(frame[4:], uint32(len(payload)))
	return append(append(frame, payload...), body...)
}

func TestOpenLogBody_DetectsFormatFromContent(t *testing.T) {
	tarBody := tarArchive(t, "schema.log", []byte("data"))
	gzTar, zstTar := gzCompress(t, tarBody), zstCompress(t, tarBody)
	gzLog, zstLog := gzCompress(t, []byte("log line\n")), zstCompress(t, []byte("log line\n"))
	skippableTar, skippableLog := withSkippableFrame(zstTar), withSkippableFrame(zstLog)
	plain := []byte("plain log line\n")

	tests := []struct {
		name           string
		logName        string
		body           []byte
		wantCompressed bool
		wantTar        bool
	}{
		{"tar.gz", "schema-logs.tar.gz", gzTar, true, true},
		{"tgz", "schema-logs.tgz", gzTar, true, true},
		{"tar.zst", "schema-logs.tar.zst", zstTar, true, true},
		{"tar.zstd", "schema-logs.tar.zstd", zstTar, true, true},
		{"gz", "node-1.log.gz", gzLog, true, false},
		{"zst", "node-1.log.zst", zstLog, true, false},
		{"zstd", "node-1.log.zstd", zstLog, true, false},
		{"uppercase tar.gz", "SCHEMA-LOGS.TAR.GZ", gzTar, true, true},
		{"uppercase gz", "NODE-1.LOG.GZ", gzLog, true, false},
		{"unknown", "events.log", plain, false, false},
		{"tar.zst body with a name without suffix", "db-node-d6b4e12c-5", zstTar, true, true},
		{"tar.gz name with a single log", "schema-logs.tar.gz", gzLog, true, false},
		{"uncompressed tar", "schema-logs.tar", tarBody, false, true},
		{"tar.zst with skippable frame", "schema-logs.tar.zst", skippableTar, true, true},
		{"zst with skippable frame", "node-1.log.zst", skippableLog, true, false},
		{"gzip body without extension", "node-1.log", gzLog, true, false},
		{"zstd body with gz name", "node-1.log.gz", zstLog, true, false},
		{"empty body", "events.log", nil, false, false},
		{"body shorter than the magic", "events.log", []byte{0x28, 0xb5}, false, false},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			lb, err := openLogBody(tc.logName, bufio.NewReader(bytes.NewReader(tc.body)))
			require.NoError(t, err)
			defer lb.close()
			assert.Equal(t, tc.wantCompressed, lb.compressed, "compressed")
			assert.Equal(t, tc.wantTar, lb.tar, "tar")
		})
	}
}

func TestOpenLogBody_RejectsCompressedNameWithoutMagic(t *testing.T) {
	tests := []struct {
		name    string
		logName string
		body    []byte
	}{
		{"zst name with plain body", "node-1.log.zst", []byte("plain log line\n")},
		{"tar.gz name with plain body", "schema-logs.tar.gz", []byte("plain log line\n")},
		{"zst name with JSON body", "node-1.log.zst", []byte(`{"status":"ok"}`)},
		{"empty body", "node-1.log.gz", nil},
		{"body shorter than the magic", "node-1.log.gz", []byte{0x28, 0xb5}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := openLogBody(tc.logName, bufio.NewReader(bytes.NewReader(tc.body)))
			require.Error(t, err)
			assert.Contains(t, err.Error(), "not gzip or zstd data")
		})
	}
}

func TestExtractBody_ExtractsTarWithNameWithoutSuffix(t *testing.T) {
	dest := t.TempDir()
	content := []byte("node log line\n")
	compressed := zstCompress(t, tarArchive(t, "db-node-5/system.log", content))

	require.NoError(t, extractBody("db-node-d6b4e12c-5", compressed, dest))

	got, err := os.ReadFile(filepath.Join(dest, "db-node-5", "system.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_WritesSingleLogWithTarNameAsFile(t *testing.T) {
	dest := t.TempDir()
	content := bytes.Repeat([]byte("plain log content, not a tar archive\n"), 20)

	require.NoError(t, extractBody("schema-logs.tar.zst", zstCompress(t, content), dest))

	got, err := os.ReadFile(filepath.Join(dest, "schema-logs.tar"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_ZstSkipsSkippableFrame(t *testing.T) {
	dest := t.TempDir()
	content := []byte("a pzstd log line\n")

	require.NoError(t, extractBody("node-1.log.zst", withSkippableFrame(zstCompress(t, content)), dest))

	got, err := os.ReadFile(filepath.Join(dest, "node-1.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestRejectErrorEnvelope_Scenarios(t *testing.T) {
	envelope := []byte(`{"status":"error","response":{"exception":"TestRunServiceException","message":"Log name x not found."}}`)

	err := rejectErrorEnvelope("application/json", bufio.NewReader(bytes.NewReader(envelope)))
	var apiErr *api.APIError
	require.ErrorAs(t, err, &apiErr)
	assert.Equal(t, "Log name x not found.", apiErr.Body.Message)

	tests := []struct {
		name        string
		contentType string
		body        []byte
	}{
		{"envelope with a non-JSON content type", "application/octet-stream", envelope},
		{"ok envelope", "application/json", []byte(`{"status":"ok","response":{}}`)},
		{"JSON log", "application/json", []byte(`{"event":"start"}`)},
		{"JSON log larger than the peek limit", "application/json", bytes.Repeat([]byte(" "), maxErrorEnvelopeSize+1)},
		{"plain text", "text/plain", []byte("plain log line\n")},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			br := bufio.NewReaderSize(bytes.NewReader(tc.body), maxErrorEnvelopeSize)
			require.NoError(t, rejectErrorEnvelope(tc.contentType, br))

			rest, err := io.ReadAll(br)
			require.NoError(t, err)
			assert.Equal(t, len(tc.body), len(rest), "the check must not consume the body")
		})
	}
}

func TestTrimCompressionSuffix_IgnoresCase(t *testing.T) {
	tests := map[string]string{
		"a.log.gz":   "a.log",
		"a.log.GZ":   "a.log",
		"a.log.zst":  "a.log",
		"a.log.ZST":  "a.log",
		"a.log.zstd": "a.log",
		"a.log.ZSTD": "a.log",
		"a.log":      "a.log",
		"a.zstd.log": "a.zstd.log",
	}
	for in, want := range tests {
		assert.Equal(t, want, trimCompressionSuffix(in), "name=%q", in)
	}
}

func TestExtractBody_ZstTrimsZstdSuffix(t *testing.T) {
	dest := t.TempDir()
	content := []byte("a zstd log line\n")

	require.NoError(t, extractBody("node-1.log.ZSTD", zstCompress(t, content), dest))

	got, err := os.ReadFile(filepath.Join(dest, "node-1.log"))
	require.NoError(t, err)
	assert.Equal(t, content, got)
}

func TestExtractBody_TarGzRejectsCorruptedGzipTrailer(t *testing.T) {
	compressed := gzCompress(t, tarArchive(t, "schema.log", []byte("data")))
	// The last 8 bytes are the CRC-32 and the size. Flip a CRC byte.
	compressed[len(compressed)-8] ^= 0xff

	dest := t.TempDir()
	err := extractBody("schema-logs.tar.gz", compressed, dest)
	require.ErrorIs(t, err, gzip.ErrChecksum)

	_, statErr := os.Stat(filepath.Join(dest, "schema.log"))
	assert.True(t, errors.Is(statErr, os.ErrNotExist), "extracted files must be removed on error")
}

func TestRejectHTMLResponse_Scenarios(t *testing.T) {
	for _, ct := range []string{"text/html", "text/html; charset=utf-8", "TEXT/HTML"} {
		err := rejectHTMLResponse(ct)
		require.Error(t, err, "contentType=%q", ct)
		assert.Contains(t, err.Error(), "HTML page")
	}
	for _, ct := range []string{"", "application/gzip", "application/octet-stream", "text/plain"} {
		assert.NoError(t, rejectHTMLResponse(ct), "contentType=%q", ct)
	}
}

func TestExtractBody_TarZstRejectsCorruptedZstdChecksum(t *testing.T) {
	compressed := zstCompress(t, tarArchive(t, "schema.log", []byte("data")))
	// The last 4 bytes are the frame checksum. Flip a checksum byte.
	compressed[len(compressed)-1] ^= 0xff

	dest := t.TempDir()
	err := extractBody("schema-logs.tar.zst", compressed, dest)
	require.Error(t, err)

	_, statErr := os.Stat(filepath.Join(dest, "schema.log"))
	assert.True(t, errors.Is(statErr, os.ErrNotExist), "extracted files must be removed on error")
}

func TestExtractBody_ZstRejectsDamagedSecondFrame(t *testing.T) {
	second := zstCompress(t, []byte("second frame\n"))
	// Flip a byte of the zstd magic of the second frame.
	second[0] ^= 0xff
	body := append(zstCompress(t, []byte("first frame\n")), second...)

	err := extractBody("node-1.log.zst", body, t.TempDir())
	require.ErrorIs(t, err, zstd.ErrMagicMismatch)
}
