// Package logging configures the zerolog-based logger for the Argus CLI.
//
// # Log destinations
//
// There are two independent log destinations:
//
//  1. File (always on) — JSON lines written to
//     $XDG_CACHE_HOME/argus-cli/argus-cli.log.  Level is controlled by the
//     --log-level flag (default: info).  JSON format allows structured
//     post-processing (e.g. jq, grep, log aggregators).  Every entry carries
//     the full field set: timestamp, level, cmd, component, caller, message.
//
//  2. Console / stderr (opt-in) — human-readable text written to whatever
//     writer is passed via [WithConsoleWriter].  Level is controlled
//     independently by the -v / -vv / -vvv flags:
//
//     -v   → error level and above
//     -vv  → info level and above
//     -vvv → debug level and above
//
//     When no -v flag is given nothing is written to stderr.
//
// The two destinations have completely independent minimum levels: a
// debug-only file level does not affect what the console shows, and vice
// versa.
//
// # Usage
//
//	logger, cleanup, err := logging.Setup("info", "argus run")
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

	// consoleTimeFormat is the timestamp layout used in console (stderr) output.
	// Shorter than the file format — milliseconds omitted for readability.
	consoleTimeFormat = "15:04:05"
)

// CleanupFunc must be called (typically via defer) to flush and close the
// underlying log file.
type CleanupFunc func()

// consoleConfig holds the configuration for the optional stderr writer.
type consoleConfig struct {
	// w is the destination writer (cobra's ErrOrStderr).
	w zerolog.LevelWriter
	// minLevel is the minimum level written to the console.
	minLevel zerolog.Level
}

// options holds optional overrides for [Setup].
type options struct {
	// writer replaces the default log-file writer. Used in tests.
	writer io.Writer
	// cacheDir overrides the directory used for the log file. Used in tests.
	cacheDir string
	// console, when non-nil, enables the stderr/console writer.
	console *consoleConfig
}

// Option is a functional option for [Setup].
type Option func(*options)

// WithWriter redirects file log output to w instead of the default on-disk
// log file.  Primarily useful in tests.
func WithWriter(w io.Writer) Option {
	return func(o *options) { o.writer = w }
}

// WithCacheDir overrides the directory in which the log file is created.
// Primarily useful in tests.
func WithCacheDir(dir string) Option {
	return func(o *options) { o.cacheDir = dir }
}

// WithConsoleWriter adds a stderr/console writer whose minimum level is
// independent of the file log level.
//
// w should be cobra's cmd.ErrOrStderr() so that the output destination is
// injectable in tests. minLevel controls what appears on the console:
//
//	zerolog.ErrorLevel → -v
//	zerolog.InfoLevel  → -vv
//	zerolog.DebugLevel → -vvv
//
// When this option is not provided, nothing is written to stderr.
func WithConsoleWriter(w io.Writer, minLevel zerolog.Level) Option {
	return func(o *options) {
		// Promote the plain io.Writer to a LevelWriter via MultiLevelWriter
		// so levelFilterWriter.WriteLevel can delegate to it properly.
		o.console = &consoleConfig{
			w:        zerolog.MultiLevelWriter(newConsoleWriter(w)),
			minLevel: minLevel,
		}
	}
}

// Setup initialises the root logger and returns it together with a cleanup
// function and any error.
//
// Parameters:
//   - fileLevelStr: minimum level written to the log file — one of "trace",
//     "debug", "info", "warn", "error" (case-insensitive).  Empty string
//     defaults to "info".
//   - command: cobra command path (e.g. "argus auth").  Stored as the "cmd"
//     field on every entry.
//
// The file writer always uses JSON format.  The console writer (if enabled via
// [WithConsoleWriter]) uses human-readable text with a short timestamp and
// ANSI colour.  The two destinations have independent minimum levels.
func Setup(fileLevelStr, command string, opts ...Option) (zerolog.Logger, CleanupFunc, error) {
	o := &options{}
	for _, fn := range opts {
		fn(o)
	}

	fileLevel, err := parseLevel(fileLevelStr)
	if err != nil {
		return zerolog.Nop(), func() {}, err
	}

	// --- file writer (JSON) ------------------------------------------
	var (
		fileW   io.Writer
		closeFn func()
	)
	if o.writer != nil {
		fileW = o.writer
		closeFn = func() {}
	} else {
		f, err := openLogFile(o.cacheDir)
		if err != nil {
			// Can't write a log file (e.g. running as nobody with no home dir).
			// Fall back to discard so the command still works.
			fileW = io.Discard
			closeFn = func() {}
		} else {
			fileW = f
			closeFn = func() { _ = f.Close() }
		}
	}

	// fileFilterWriter ensures only entries at or above fileLevel reach the
	// JSON file.  We set the root logger to TraceLevel so it never drops an
	// entry before the per-writer filters can act.
	fileLW := &levelFilterWriter{
		writer:   zerolog.MultiLevelWriter(fileW),
		minLevel: fileLevel,
	}

	// --- multi-writer ------------------------------------------------
	var logWriter zerolog.LevelWriter
	if o.console != nil {
		consoleLW := &levelFilterWriter{
			writer:   o.console.w,
			minLevel: o.console.minLevel,
		}
		logWriter = zerolog.MultiLevelWriter(fileLW, consoleLW)
	} else {
		logWriter = zerolog.MultiLevelWriter(fileLW)
	}

	// Root logger at TraceLevel so per-writer filters are the sole gatekeepers.
	root := zerolog.New(logWriter).
		Level(zerolog.TraceLevel).
		With().
		Timestamp().
		Str("cmd", command).
		Logger()

	// Boundary markers in the file help scanning across multiple invocations.
	root.Info().
		Str("file_level", fileLevel.String()).
		Msgf("--- argus %s started ---", command)

	cleanup := func() {
		root.Info().Msgf("--- argus %s finished ---", command)
		closeFn()
	}

	return root, cleanup, nil
}

// For returns a sub-logger scoped to a named component, inheriting the level
// and writers of the parent. The "component" field is added (or overwritten).
//
//	authLogger := logging.For(root, "auth")
//	authLogger.Debug().Msg("requesting CF token")
func For(parent zerolog.Logger, component string) zerolog.Logger {
	return parent.With().Str("component", component).Logger()
}

// --------------------------------------------------------------------------
// internal helpers
// --------------------------------------------------------------------------

// levelFilterWriter wraps a zerolog.LevelWriter and suppresses entries whose
// level is below minLevel.  This is how the file and console destinations
// enforce their independent minimum levels without needing two logger
// instances.
type levelFilterWriter struct {
	writer   zerolog.LevelWriter
	minLevel zerolog.Level
}

// Write satisfies io.Writer; called for level-less raw writes — always passed
// through (no filtering possible without a level).
func (f *levelFilterWriter) Write(p []byte) (int, error) {
	return f.writer.Write(p)
}

// WriteLevel satisfies zerolog.LevelWriter; called by zerolog for every
// structured log entry.  Entries below minLevel are silently discarded.
func (f *levelFilterWriter) WriteLevel(l zerolog.Level, p []byte) (int, error) {
	if l < f.minLevel {
		return len(p), nil
	}
	return f.writer.WriteLevel(l, p)
}

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

	// Only create the directory if it doesn't already exist — never force-create
	// it (e.g. when running as nobody with no writable home).
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		if mkErr := os.MkdirAll(dir, 0o750); mkErr != nil {
			return nil, fmt.Errorf("%w: creating cache dir %q: %w", ErrOpeningLogFile, dir, mkErr)
		}
	}

	p := filepath.Join(dir, LogFileName)
	f, err := os.OpenFile(p, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o640)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrOpeningLogFile, p, err)
	}
	return f, nil
}

// newConsoleWriter returns a zerolog ConsoleWriter for human-readable stderr
// output.
//
// Format:  HH:MM:SS LVL message  key=value …
//
// Colour is always enabled — the console writer is only instantiated when
// WithConsoleWriter is called, which is only done when a real TTY-capable
// writer (cobra's ErrOrStderr) is provided.  Tests that need to assert on
// console output should pass a plain bytes.Buffer and inspect the text
// content rather than relying on colour codes.
//
// The field set is intentionally minimal: timestamp, level, and message.
// Structured fields (cmd, component, etc.) are still printed but without
// verbose key prefixes so the output stays readable at a glance.
func newConsoleWriter(w io.Writer) zerolog.ConsoleWriter {
	cw := zerolog.ConsoleWriter{
		Out:        w,
		NoColor:    false,
		TimeFormat: consoleTimeFormat,
	}

	cw.FormatTimestamp = func(i any) string {
		if t, ok := i.(string); ok {
			// zerolog stores timestamps as formatted strings when using
			// ConsoleWriter — re-parse and reformat to our short layout.
			parsed, err := time.Parse(time.RFC3339, t)
			if err != nil {
				return t
			}
			return parsed.Format(consoleTimeFormat)
		}
		return time.Now().Format(consoleTimeFormat)
	}

	// Omit the "cmd" field from console output — it is always visible from
	// context and clutters the short per-line format.
	cw.FieldsExclude = []string{"cmd", "file_level"}

	return cw
}
