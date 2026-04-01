// Package logging configures the zerolog-based logger for the Argus CLI.
//
// Every invocation appends to a single rotating log file stored in the XDG
// cache directory ($XDG_CACHE_HOME/argus-cli/argus-cli.log). Output is
// human-readable text (zerolog ConsoleWriter) rather than JSON.
//
// Usage pattern:
//
//	logger, cleanup, err := logging.Setup("info", "run")
//	defer cleanup()
//	sub := logging.For(logger, "keychain")
//	sub.Info().Msg("storing session")
package logging

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/rs/zerolog"

	"github.com/scylladb/argus/cli/internal/config"
)

// Sentinel errors returned by this package.
var (
	// ErrInvalidLevel is returned when the supplied log-level string does not
	// map to a known zerolog.Level.
	ErrInvalidLevel = errors.New("logging: invalid log level")

	// ErrOpeningLogFile is returned when the log file cannot be opened or
	// created.
	ErrOpeningLogFile = errors.New("logging: opening log file")
)

const (
	// LogFileName is the name of the append-only log file written to the XDG
	// cache directory.
	LogFileName = "argus-cli.log"

	// timeFormat is the timestamp layout used in every log line.
	// Example: 2026-03-22 14:05:03.412
	timeFormat = "2006-01-02 15:04:05.000"
)

// CleanupFunc must be called (typically via defer) to flush and close the
// underlying log file.
type CleanupFunc func()

// options holds optional overrides for [Setup].
type options struct {
	// writer replaces the default log-file writer. Used in tests.
	writer io.Writer
	// stderrWriter overrides the stderr writer used for error-and-above output.
	// Defaults to os.Stderr. Used in tests.
	stderrWriter io.Writer
	// cacheDir overrides the directory used for the log file. Used in tests
	// to avoid depending on the XDG cache path which is resolved at init time.
	cacheDir string
}

// Option is a functional option for [Setup].
type Option func(*options)

// WithWriter redirects log output to w instead of the default on-disk file.
// Primarily useful in tests.
func WithWriter(w io.Writer) Option {
	return func(o *options) { o.writer = w }
}

// WithStderrWriter overrides the writer used for error-and-above output.
// Primarily useful in tests.
func WithStderrWriter(w io.Writer) Option {
	return func(o *options) { o.stderrWriter = w }
}

// WithCacheDir overrides the directory in which the log file is created.
// Primarily useful in tests where the XDG cache dir is not writable or has
// already been resolved to the wrong path.
func WithCacheDir(dir string) Option {
	return func(o *options) { o.cacheDir = dir }
}

// Setup initialises the root logger and returns it together with a cleanup
// function and any error.
//
// Parameters:
//   - levelStr: one of "trace", "debug", "info", "warn", "error", "fatal",
//     "panic" (case-insensitive). Empty string defaults to "info".
//   - command:  the cobra command path (e.g. "argus auth"). Stored as the
//     "cmd" field on every log entry emitted through the returned logger.
//
// The log file is opened in append + create mode so multiple CLI invocations
// accumulate in the same file. The returned CleanupFunc closes the file.
func Setup(levelStr, command string, opts ...Option) (zerolog.Logger, CleanupFunc, error) {
	o := &options{}
	for _, fn := range opts {
		fn(o)
	}

	level, err := parseLevel(levelStr)
	if err != nil {
		return zerolog.Nop(), func() {}, err
	}

	var (
		w       io.Writer
		closeFn func()
	)

	if o.writer != nil {
		w = o.writer
		closeFn = func() {}
	} else {
		f, err := openLogFile(o.cacheDir)
		if err != nil {
			return zerolog.Nop(), func() {}, err
		}
		w = f
		closeFn = func() { _ = f.Close() }
	}

	// All log entries go to the file (or injected writer).
	fileWriter := newConsoleWriter(w)

	// Messages at or above the configured level are also mirrored to stderr
	// so the user sees them in the terminal without having to tail the log file.
	stderrDst := o.stderrWriter
	if stderrDst == nil {
		stderrDst = os.Stderr
	}
	stderrWriter := &levelFilterWriter{
		min: level,
		cw:  newConsoleWriter(stderrDst),
	}

	writer := zerolog.MultiLevelWriter(fileWriter, stderrWriter)

	root := zerolog.New(writer).
		Level(level).
		With().
		Timestamp().
		Str("cmd", command).
		Logger()

	// Log the invocation boundary so the file is easy to scan.
	root.Info().
		Str("level", level.String()).
		Msgf("--- argus %s started ---", command)

	cleanup := func() {
		root.Info().Msgf("--- argus %s finished ---", command)
		closeFn()
	}

	return root, cleanup, nil
}

// For returns a sub-logger scoped to a named component, inheriting the level
// and writers of the parent. All fields already present on parent are
// preserved; "component" is added (or overwritten) as a new field.
//
//	authLogger := logging.For(root, "auth")
//	authLogger.Debug().Msg("requesting CF token")
func For(parent zerolog.Logger, component string) zerolog.Logger {
	return parent.With().Str("component", component).Logger()
}

// --------------------------------------------------------------------------
// internal helpers
// --------------------------------------------------------------------------

func parseLevel(s string) (zerolog.Level, error) {
	if s == "" {
		return zerolog.InfoLevel, nil
	}
	level, err := zerolog.ParseLevel(strings.ToLower(s))
	if err != nil {
		return zerolog.NoLevel, fmt.Errorf("%w %q: %w", ErrInvalidLevel, s, err)
	}
	return level, nil
}

func openLogFile(cacheDir string) (*os.File, error) {
	dir := cacheDir
	if dir == "" {
		dir = config.CacheDir()
	}
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return nil, fmt.Errorf("%w: creating cache dir %q: %w", ErrOpeningLogFile, dir, err)
	}

	path := filepath.Join(dir, LogFileName)
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o640)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrOpeningLogFile, path, err)
	}
	return f, nil
}

// newConsoleWriter returns a zerolog ConsoleWriter that writes human-readable
// log lines to w.
//
// Line format (fixed-width fields, no colour — colour codes look like garbage
// in a plain file):
//
//	2026-03-22 14:05:03.412 INF cmd=auth component=keychain message text
func newConsoleWriter(w io.Writer) zerolog.ConsoleWriter {
	cw := zerolog.ConsoleWriter{
		Out:        w,
		NoColor:    true,
		TimeFormat: timeFormat,
	}

	cw.FormatTimestamp = func(i any) string {
		if t, ok := i.(string); ok {
			return t
		}
		return time.Now().Format(timeFormat)
	}

	return cw
}

// levelFilterWriter is a zerolog.LevelWriter that forwards log entries to cw
// only when their level is >= min. This lets us attach a stderr sink that
// surfaces errors to the terminal without duplicating info/debug output.
type levelFilterWriter struct {
	min zerolog.Level
	cw  zerolog.ConsoleWriter
}

// Write implements io.Writer. zerolog calls this for level-less writes (e.g.
// the raw JSON before level routing); we drop them here — WriteLevel is the
// real entry point.
func (f *levelFilterWriter) Write(p []byte) (int, error) {
	return len(p), nil
}

// WriteLevel implements zerolog.LevelWriter. Only entries at or above f.min
// are forwarded to the underlying ConsoleWriter.
func (f *levelFilterWriter) WriteLevel(l zerolog.Level, p []byte) (int, error) {
	if l < f.min {
		return len(p), nil
	}
	return f.cw.Write(p)
}
