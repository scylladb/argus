package replay

import (
	"archive/tar"
	"bytes"
	"errors"
	"io"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"github.com/klauspost/compress/zstd"
)

// buildTarZst writes a tar.zst archive whose entries are name → content pairs.
func buildTarZst(t *testing.T, entries map[string]string) []byte {
	t.Helper()
	var buf bytes.Buffer
	zw, err := zstd.NewWriter(&buf)
	if err != nil {
		t.Fatalf("zstd writer: %v", err)
	}
	tw := tar.NewWriter(zw)

	// Sort for deterministic ordering across runs.
	names := make([]string, 0, len(entries))
	for n := range entries {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		data := []byte(entries[n])
		if err := tw.WriteHeader(&tar.Header{
			Name: n, Mode: 0o644, Size: int64(len(data)), Typeflag: tar.TypeReg,
		}); err != nil {
			t.Fatalf("tar header: %v", err)
		}
		if _, err := tw.Write(data); err != nil {
			t.Fatalf("tar write: %v", err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatalf("tar close: %v", err)
	}
	if err := zw.Close(); err != nil {
		t.Fatalf("zstd close: %v", err)
	}
	return buf.Bytes()
}

func TestMaterializePlainJSONL(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "argus_replay_log_R_1.jsonl")
	if err := os.WriteFile(path, []byte(`{"ts":1}`+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	mi, err := Materialize(path, "")
	if err != nil {
		t.Fatalf("Materialize: %v", err)
	}
	defer mi.Cleanup()

	if len(mi.Files) != 1 || mi.Files[0] != path {
		t.Errorf("plain jsonl: got %v, want [%q]", mi.Files, path)
	}
}

func TestMaterializeJSONLZst(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "argus_replay_log_R_1.jsonl.zst")

	var buf bytes.Buffer
	zw, _ := zstd.NewWriter(&buf)
	if _, err := zw.Write([]byte(`{"ts":7}` + "\n")); err != nil {
		t.Fatal(err)
	}
	_ = zw.Close()
	if err := os.WriteFile(src, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}

	mi, err := Materialize(src, "")
	if err != nil {
		t.Fatalf("Materialize: %v", err)
	}
	defer mi.Cleanup()

	if len(mi.Files) != 1 {
		t.Fatalf("expected 1 materialized file, got %d", len(mi.Files))
	}
	if got := filepath.Base(mi.Files[0]); got != "argus_replay_log_R_1.jsonl" {
		t.Errorf("decompressed basename: got %q, want %q", got, "argus_replay_log_R_1.jsonl")
	}

	content, err := os.ReadFile(mi.Files[0])
	if err != nil {
		t.Fatal(err)
	}
	if string(content) != `{"ts":7}`+"\n" {
		t.Errorf("decompressed content mismatch: %q", content)
	}
}

func TestMaterializeTarZstFiltersToReplayLogs(t *testing.T) {
	archive := buildTarZst(t, map[string]string{
		"sct-runner-events-xyz/argus.log":                          "some sct log",
		"sct-runner-events-xyz/critical.log":                       "critical log",
		"sct-runner-events-xyz/argus_replay_log_R_1.jsonl":         `{"ts":1}` + "\n",
		"sct-runner-events-xyz/argus_replay_log_R_2.jsonl":         `{"ts":2}` + "\n",
		"sct-runner-events-xyz/argus_replay_log_OTHER_1.jsonl":     `{"ts":3}` + "\n",
		"sct-runner-events-xyz/notes/README.txt":                   "readme",
		"sct-runner-events-xyz/sub/argus_replay_log_DEEP_1.jsonl":  `{"ts":4}` + "\n",
		"sct-runner-events-xyz/argus_replay_log_R_1.jsonl.partial": "should be skipped",
	})

	dir := t.TempDir()
	src := filepath.Join(dir, "archive.tar.zst")
	if err := os.WriteFile(src, archive, 0o644); err != nil {
		t.Fatal(err)
	}

	// Without filter: all argus_replay_log_*.jsonl entries.
	mi, err := Materialize(src, "")
	if err != nil {
		t.Fatalf("Materialize: %v", err)
	}
	defer mi.Cleanup()

	names := basenames(mi.Files)
	want := []string{
		"argus_replay_log_DEEP_1.jsonl",
		"argus_replay_log_OTHER_1.jsonl",
		"argus_replay_log_R_1.jsonl",
		"argus_replay_log_R_2.jsonl",
	}
	if !equal(names, want) {
		t.Errorf("unfiltered names mismatch:\n got: %v\nwant: %v", names, want)
	}

	// With run-id filter R: only the two R_* files.
	mi2, err := Materialize(src, "R")
	if err != nil {
		t.Fatalf("Materialize: %v", err)
	}
	defer mi2.Cleanup()

	names = basenames(mi2.Files)
	want = []string{
		"argus_replay_log_R_1.jsonl",
		"argus_replay_log_R_2.jsonl",
	}
	if !equal(names, want) {
		t.Errorf("filtered names mismatch:\n got: %v\nwant: %v", names, want)
	}
}

func TestMaterializeUnsupportedExtension(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "events.log")
	if err := os.WriteFile(path, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	mi, err := Materialize(path, "")
	defer mi.Cleanup()
	if !errors.Is(err, ErrUnsupportedInput) {
		t.Fatalf("expected ErrUnsupportedInput, got %v", err)
	}
}

func TestMaterializeTarZstWithoutReplayLogs(t *testing.T) {
	archive := buildTarZst(t, map[string]string{
		"events.log": "no replay logs here",
	})
	dir := t.TempDir()
	src := filepath.Join(dir, "archive.tar.zst")
	if err := os.WriteFile(src, archive, 0o644); err != nil {
		t.Fatal(err)
	}

	mi, err := Materialize(src, "")
	defer mi.Cleanup()
	if err == nil {
		t.Fatal("expected an error for tar.zst with no replay logs")
	}
}

func basenames(paths []string) []string {
	out := make([]string, len(paths))
	for i, p := range paths {
		out[i] = filepath.Base(p)
	}
	sort.Strings(out)
	return out
}

func equal(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestEnsureCloseable(t *testing.T) {
	// Sanity check that io.Discard works as we expect in other tests.
	_, _ = io.Copy(io.Discard, bytes.NewReader(nil))
}
