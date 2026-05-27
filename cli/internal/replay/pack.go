// Package replay packages JSONL replay-log files into the `tar.zst`
// archive format accepted by the Argus replay-ingest endpoint.
//
// See docs/plans/request_replay.md for the wire-level details.
package replay

import (
	"archive/tar"
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/klauspost/compress/zstd"
)

// ErrNoFiles is returned by Pack when files is empty.
var ErrNoFiles = errors.New("replay: no files to pack")

// ErrInvalidJSONL signals that a line inside one of the input files is not a
// valid JSON object. The full message includes the file basename and 1-indexed
// line number.
var ErrInvalidJSONL = errors.New("replay: invalid JSONL line")

// Pack reads each path in files, validates every line as a JSON object, and
// streams a tar.zst archive containing one entry per file to w. Each tar entry
// uses the source filename's basename as its name so the server can recover the
// `argus_replay_log_{run_id}_{unix_ms}.jsonl` convention.
//
// Validation is line-by-line: a single malformed line aborts the pack with
// ErrInvalidJSONL wrapped around the file path and line number. No partial
// archive is emitted because the tar/zstd writers are closed before Pack
// returns; the caller is responsible for handling any bytes already written to
// w on error (typically by tearing down the io.Pipe).
func Pack(files []string, w io.Writer) error {
	if len(files) == 0 {
		return ErrNoFiles
	}

	zw, err := zstd.NewWriter(w)
	if err != nil {
		return fmt.Errorf("replay: zstd writer: %w", err)
	}
	tw := tar.NewWriter(zw)

	for _, path := range files {
		if err := addFile(tw, path); err != nil {
			_ = tw.Close()
			_ = zw.Close()
			return err
		}
	}

	if err := tw.Close(); err != nil {
		_ = zw.Close()
		return fmt.Errorf("replay: closing tar: %w", err)
	}
	if err := zw.Close(); err != nil {
		return fmt.Errorf("replay: closing zstd: %w", err)
	}
	return nil
}

// addFile validates path as JSONL and writes it as a single tar entry.
//
// The file is read twice: once with bufio.Scanner for line-by-line
// validation, then a second time by io.Copy for the actual bytes. This is
// simpler than buffering the whole file in memory and the second read is
// cheap (page cache is warm).
func addFile(tw *tar.Writer, path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("replay: stat %q: %w", path, err)
	}
	if info.IsDir() {
		return fmt.Errorf("replay: %q is a directory", path)
	}

	if err := validateJSONL(path); err != nil {
		return err
	}

	hdr := &tar.Header{
		Name:    filepath.Base(path),
		Mode:    0o644,
		Size:    info.Size(),
		ModTime: info.ModTime().UTC().Truncate(time.Second),
	}
	if err := tw.WriteHeader(hdr); err != nil {
		return fmt.Errorf("replay: tar header for %q: %w", path, err)
	}

	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("replay: open %q: %w", path, err)
	}
	defer func() { _ = f.Close() }()

	if _, err := io.Copy(tw, f); err != nil {
		return fmt.Errorf("replay: writing %q to tar: %w", path, err)
	}
	return nil
}

// validateJSONL ensures every non-empty line in path is a JSON object.
// Empty lines are tolerated (trailing newlines from the writer thread).
func validateJSONL(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("replay: open %q: %w", path, err)
	}
	defer func() { _ = f.Close() }()

	scanner := bufio.NewScanner(f)
	// Replay records can be large (full event payloads, junit reports).
	// Allow up to 16 MiB per line — same order of magnitude the Python
	// writer can emit before the request itself fails.
	const maxLine = 16 * 1024 * 1024
	buf := make([]byte, 0, 64*1024)
	scanner.Buffer(buf, maxLine)

	lineNo := 0
	for scanner.Scan() {
		lineNo++
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var v map[string]any
		if err := json.Unmarshal(line, &v); err != nil {
			return fmt.Errorf("%w: %s:%d: %w",
				ErrInvalidJSONL, filepath.Base(path), lineNo, err)
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("replay: scanning %q: %w", path, err)
	}
	return nil
}
