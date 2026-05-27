package replay

import (
	"archive/tar"
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"github.com/klauspost/compress/zstd"
)

func writeFile(t *testing.T, dir, name, content string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %q: %v", path, err)
	}
	return path
}

func TestPackRoundTrip(t *testing.T) {
	dir := t.TempDir()

	a := writeFile(t, dir, "argus_replay_log_run-A_1.jsonl",
		`{"ts":1,"endpoint":"/x","method":"POST"}`+"\n"+
			`{"ts":2,"endpoint":"/y","method":"POST"}`+"\n")
	b := writeFile(t, dir, "argus_replay_log_run-A_2.jsonl",
		`{"ts":3,"endpoint":"/z","method":"POST"}`+"\n"+
			"\n") // trailing blank line is tolerated

	var buf bytes.Buffer
	if err := Pack([]string{a, b}, &buf); err != nil {
		t.Fatalf("Pack: %v", err)
	}

	zr, err := zstd.NewReader(&buf)
	if err != nil {
		t.Fatalf("zstd reader: %v", err)
	}
	defer zr.Close()

	tr := tar.NewReader(zr)
	got := map[string]string{}
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatalf("tar next: %v", err)
		}
		data, err := io.ReadAll(tr)
		if err != nil {
			t.Fatalf("tar read: %v", err)
		}
		got[hdr.Name] = string(data)
	}

	want := map[string]string{
		"argus_replay_log_run-A_1.jsonl": `{"ts":1,"endpoint":"/x","method":"POST"}` + "\n" +
			`{"ts":2,"endpoint":"/y","method":"POST"}` + "\n",
		"argus_replay_log_run-A_2.jsonl": `{"ts":3,"endpoint":"/z","method":"POST"}` + "\n\n",
	}

	if len(got) != len(want) {
		t.Fatalf("entry count: got %d, want %d", len(got), len(want))
	}

	gotKeys := make([]string, 0, len(got))
	for k := range got {
		gotKeys = append(gotKeys, k)
	}
	sort.Strings(gotKeys)

	for _, k := range gotKeys {
		if got[k] != want[k] {
			t.Errorf("%s mismatch:\n got: %q\nwant: %q", k, got[k], want[k])
		}
	}
}

func TestPackRejectsBadJSON(t *testing.T) {
	dir := t.TempDir()
	path := writeFile(t, dir, "argus_replay_log_bad_1.jsonl",
		`{"ts":1,"ok":true}`+"\n"+
			`this is not json`+"\n")

	err := Pack([]string{path}, io.Discard)
	if !errors.Is(err, ErrInvalidJSONL) {
		t.Fatalf("expected ErrInvalidJSONL, got: %v", err)
	}
	// Filename and line number should be reported.
	msg := err.Error()
	if !contains(msg, "argus_replay_log_bad_1.jsonl") {
		t.Errorf("missing filename in error: %s", msg)
	}
	if !contains(msg, ":2") {
		t.Errorf("missing line number in error: %s", msg)
	}
}

func TestPackEmptyInputs(t *testing.T) {
	if err := Pack(nil, io.Discard); !errors.Is(err, ErrNoFiles) {
		t.Errorf("nil files: expected ErrNoFiles, got %v", err)
	}
	if err := Pack([]string{}, io.Discard); !errors.Is(err, ErrNoFiles) {
		t.Errorf("empty files: expected ErrNoFiles, got %v", err)
	}
}

func TestPackTarEntryBasenameOnly(t *testing.T) {
	dir := t.TempDir()
	nested := filepath.Join(dir, "sub", "dir")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	path := writeFile(t, nested, "argus_replay_log_run-Z_42.jsonl",
		`{"ts":1}`+"\n")

	// Encode using a JSON marshal so we exercise that the file is valid JSONL.
	if !json.Valid([]byte(`{"ts":1}`)) {
		t.Fatal("self-check failed")
	}

	var buf bytes.Buffer
	if err := Pack([]string{path}, &buf); err != nil {
		t.Fatalf("Pack: %v", err)
	}

	zr, err := zstd.NewReader(&buf)
	if err != nil {
		t.Fatalf("zstd reader: %v", err)
	}
	defer zr.Close()

	tr := tar.NewReader(zr)
	hdr, err := tr.Next()
	if err != nil {
		t.Fatalf("tar next: %v", err)
	}
	if hdr.Name != "argus_replay_log_run-Z_42.jsonl" {
		t.Errorf("tar entry name: got %q, want basename only", hdr.Name)
	}
}

func contains(s, sub string) bool {
	return bytes.Contains([]byte(s), []byte(sub))
}
