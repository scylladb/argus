package replay

import (
	"archive/tar"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/klauspost/compress/zstd"
)

// ReplayFileNamePattern matches an argus replay log filename, with or without
// a trailing .zst[d] suffix. Group "run" is the run UUID; group "ts" is the
// init-timestamp in unix-ms.
var ReplayFileNamePattern = regexp.MustCompile(
	`^argus_replay_log_(?P<run>[^/]+?)_(?P<ts>\d+)\.jsonl(?:\.zstd?)?$`,
)

// ErrUnsupportedInput is returned when the user passes a path whose extension
// the CLI does not know how to decode (anything other than .jsonl, .zst,
// .zstd, .tar.zst, .tar.zstd).
var ErrUnsupportedInput = errors.New("replay: unsupported input format")

// MaterializedInput is the result of normalising one user-supplied path into
// zero or more plain-JSONL files ready for Pack. Cleanup removes any temp
// directories created during materialisation and is safe to call multiple
// times.
type MaterializedInput struct {
	Files   []string
	Cleanup func()
}

// Materialize decodes one input path into plain JSONL file paths.
//
//   - `*.tar.zst` / `*.tar.zstd` is extracted into a temp directory; only
//     entries whose basename matches ReplayFileNamePattern are returned.
//   - `*.jsonl.zst` / `*.jsonl.zstd` is decompressed to a temp file whose
//     name drops the .zst suffix.
//   - `*.jsonl` is returned as-is (no copy).
//   - Anything else returns ErrUnsupportedInput.
//
// When runIDFilter is non-empty, only files whose ReplayFileNamePattern "run"
// group matches the filter are kept (applies inside tar.zst archives too).
// The returned MaterializedInput.Cleanup is non-nil and always safe to call,
// even on error.
func Materialize(path, runIDFilter string) (*MaterializedInput, error) {
	noop := func() {}
	base := filepath.Base(path)

	switch {
	case strings.HasSuffix(base, ".tar.zst") || strings.HasSuffix(base, ".tar.zstd"):
		return materializeTarZst(path, runIDFilter)

	case strings.HasSuffix(base, ".jsonl.zst") || strings.HasSuffix(base, ".jsonl.zstd"):
		return materializeJSONLZst(path, runIDFilter)

	case strings.HasSuffix(base, ".jsonl"):
		if !matchesRunID(base, runIDFilter) {
			return &MaterializedInput{Cleanup: noop}, nil
		}
		return &MaterializedInput{Files: []string{path}, Cleanup: noop}, nil

	default:
		return &MaterializedInput{Cleanup: noop},
			fmt.Errorf("%w: %q (expected .jsonl, .jsonl.zst, .tar.zst)", ErrUnsupportedInput, path)
	}
}

// matchesRunID reports whether basename's run-id captures equal want. Files
// that don't match ReplayFileNamePattern are kept (the user passed them
// explicitly with --file, so we trust them); when want is empty all files
// match.
func matchesRunID(basename, want string) bool {
	if want == "" {
		return true
	}
	m := ReplayFileNamePattern.FindStringSubmatch(basename)
	if m == nil {
		return true
	}
	return m[ReplayFileNamePattern.SubexpIndex("run")] == want
}

func materializeJSONLZst(path, runIDFilter string) (*MaterializedInput, error) {
	noop := func() {}
	base := filepath.Base(path)
	// Strip the trailing .zst or .zstd to recover the .jsonl name we'll
	// hand to Pack.
	jsonlName := strings.TrimSuffix(base, ".zstd")
	jsonlName = strings.TrimSuffix(jsonlName, ".zst")

	if !matchesRunID(jsonlName, runIDFilter) {
		return &MaterializedInput{Cleanup: noop}, nil
	}

	dir, err := os.MkdirTemp("", "argus-replay-*")
	if err != nil {
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: temp dir: %w", err)
	}
	cleanup := func() { _ = os.RemoveAll(dir) }

	in, err := os.Open(path)
	if err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: open %q: %w", path, err)
	}
	defer func() { _ = in.Close() }()

	zr, err := zstd.NewReader(in)
	if err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: zstd reader for %q: %w", path, err)
	}
	defer zr.Close()

	out := filepath.Join(dir, jsonlName)
	dst, err := os.Create(out)
	if err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: create %q: %w", out, err)
	}
	if _, err := io.Copy(dst, zr); err != nil {
		_ = dst.Close()
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: decompressing %q: %w", path, err)
	}
	if err := dst.Close(); err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: closing %q: %w", out, err)
	}
	return &MaterializedInput{Files: []string{out}, Cleanup: cleanup}, nil
}

func materializeTarZst(path, runIDFilter string) (*MaterializedInput, error) {
	noop := func() {}

	dir, err := os.MkdirTemp("", "argus-replay-*")
	if err != nil {
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: temp dir: %w", err)
	}
	cleanup := func() { _ = os.RemoveAll(dir) }

	in, err := os.Open(path)
	if err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: open %q: %w", path, err)
	}
	defer func() { _ = in.Close() }()

	zr, err := zstd.NewReader(in)
	if err != nil {
		cleanup()
		return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: zstd reader for %q: %w", path, err)
	}
	defer zr.Close()

	var files []string
	tr := tar.NewReader(zr)
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			cleanup()
			return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: tar entry in %q: %w", path, err)
		}
		if hdr.Typeflag != tar.TypeReg {
			continue
		}
		base := filepath.Base(hdr.Name)
		// Only keep entries that look like argus replay logs.
		if !strings.HasPrefix(base, "argus_replay_log_") || !strings.HasSuffix(base, ".jsonl") {
			continue
		}
		if !matchesRunID(base, runIDFilter) {
			continue
		}

		// Write into the temp dir using the basename only — extracted
		// paths must not preserve directory structure from the archive.
		out := filepath.Join(dir, base)
		dst, err := os.Create(out)
		if err != nil {
			cleanup()
			return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: create %q: %w", out, err)
		}
		if _, err := io.Copy(dst, tr); err != nil {
			_ = dst.Close()
			cleanup()
			return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: extracting %q from %q: %w", base, path, err)
		}
		if err := dst.Close(); err != nil {
			cleanup()
			return &MaterializedInput{Cleanup: noop}, fmt.Errorf("replay: closing %q: %w", out, err)
		}
		files = append(files, out)
	}

	if len(files) == 0 {
		cleanup()
		if runIDFilter != "" {
			return &MaterializedInput{Cleanup: noop},
				fmt.Errorf("replay: no argus_replay_log_%s_*.jsonl entries in %q", runIDFilter, path)
		}
		return &MaterializedInput{Cleanup: noop},
			fmt.Errorf("replay: no argus_replay_log_*.jsonl entries in %q", path)
	}
	return &MaterializedInput{Files: files, Cleanup: cleanup}, nil
}
