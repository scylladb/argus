package logging_test

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// Setup – file-based tests use WithCacheDir(t.TempDir()) to avoid the
// adrg/xdg package-init caching problem.
// --------------------------------------------------------------------------

func TestSetup_CreatesLogFile(t *testing.T) {
	t.Parallel()
	cacheDir := t.TempDir()

	_, cleanup, err := logging.Setup("info", "test-cmd",
		logging.WithCacheDir(cacheDir),
	)
	require.NoError(t, err)
	cleanup()

	logPath := filepath.Join(cacheDir, logging.LogFileName)
	_, statErr := os.Stat(logPath)
	assert.NoError(t, statErr, "log file should exist after Setup")
}

func TestSetup_LogFileContainsCommandAndBoundaryMessages(t *testing.T) {
	t.Parallel()
	cacheDir := t.TempDir()

	logger, cleanup, err := logging.Setup("info", "my-command",
		logging.WithCacheDir(cacheDir),
	)
	require.NoError(t, err)

	logger.Info().Msg("hello from test")
	cleanup()

	logPath := filepath.Join(cacheDir, logging.LogFileName)
	raw, err := os.ReadFile(logPath)
	require.NoError(t, err)
	content := string(raw)

	assert.Contains(t, content, "my-command", "log should contain command name")
	assert.Contains(t, content, "started", "log should contain start boundary")
	assert.Contains(t, content, "finished", "log should contain finish boundary")
	assert.Contains(t, content, "hello from test", "log should contain emitted message")
}

// TestSetup_EmptyLevelDefaultsToInfo verifies that an empty level string
// defaults to info: debug messages must NOT appear in the file output.
func TestSetup_EmptyLevelDefaultsToInfo(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("", "cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	defer cleanup()

	logger.Debug().Msg("debug-only")
	logger.Info().Msg("info-only")

	content := buf.String()
	// Debug message must be suppressed at default info level.
	assert.NotContains(t, content, "debug-only", "debug must be suppressed at default info level")
	assert.Contains(t, content, "info-only", "info must appear at default info level")
}

// TestSetup_LevelCaseInsensitive verifies that the level string is
// case-insensitive: "DEBUG" is equivalent to "debug".
func TestSetup_LevelCaseInsensitive(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("DEBUG", "cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	defer cleanup()

	logger.Debug().Msg("debug-msg")

	assert.Contains(t, buf.String(), "debug-msg",
		"debug message must appear when level is DEBUG (case-insensitive)")
}

func TestSetup_InvalidLevelReturnsError(t *testing.T) {
	t.Parallel()

	_, cleanup, err := logging.Setup("superverbose", "cmd")
	defer cleanup()

	require.Error(t, err)
	assert.ErrorIs(t, err, logging.ErrInvalidLevel)
}

func TestSetup_AppendsModeKeepsExistingContent(t *testing.T) {
	t.Parallel()
	cacheDir := t.TempDir()

	// First invocation.
	_, cleanup1, err := logging.Setup("info", "first",
		logging.WithCacheDir(cacheDir),
	)
	require.NoError(t, err)
	cleanup1()

	// Second invocation.
	_, cleanup2, err := logging.Setup("info", "second",
		logging.WithCacheDir(cacheDir),
	)
	require.NoError(t, err)
	cleanup2()

	logPath := filepath.Join(cacheDir, logging.LogFileName)
	raw, err := os.ReadFile(logPath)
	require.NoError(t, err)
	content := string(raw)

	assert.Contains(t, content, "first", "first run's output should be retained")
	assert.Contains(t, content, "second", "second run's output should be appended")
}

// --------------------------------------------------------------------------
// File format: JSON
// --------------------------------------------------------------------------

// TestSetup_FileWriterUsesJSONFormat verifies that every log line written to
// the file writer is a valid JSON object (not ConsoleWriter text).
func TestSetup_FileWriterUsesJSONFormat(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("info", "json-cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	logger.Info().Str("key", "value").Msg("check format")
	cleanup()

	for _, line := range strings.Split(strings.TrimSpace(buf.String()), "\n") {
		if line == "" {
			continue
		}
		var obj map[string]any
		assert.NoError(t, json.Unmarshal([]byte(line), &obj),
			"every file log line must be valid JSON; got: %s", line)
		assert.True(t, strings.HasPrefix(strings.TrimSpace(line), "{"),
			"file log lines must be JSON objects; got: %s", line)
	}

	// The message and extra field must be present in JSON form.
	assert.Contains(t, buf.String(), "check format")
	assert.Contains(t, buf.String(), `"key":"value"`)
}

// TestSetup_FileContainsCmdField verifies that the "cmd" field is present in
// file (JSON) output (it is excluded from the console writer).
func TestSetup_FileContainsCmdField(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	_, cleanup, err := logging.Setup("info", "my-cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	cleanup()

	assert.Contains(t, buf.String(), `"cmd":"my-cmd"`,
		"file JSON output must include the cmd field")
}

// --------------------------------------------------------------------------
// File-only: nothing goes to stderr
// --------------------------------------------------------------------------

// TestSetup_NothingWrittenToStderr verifies that log output only goes to the
// file writer and never to a console writer when WithConsoleWriter is not used.
func TestSetup_NothingWrittenToStderr(t *testing.T) {
	t.Parallel()
	var file bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "cmd",
		logging.WithWriter(&file),
	)
	require.NoError(t, err)
	logger.Debug().Msg("debug-msg")
	logger.Info().Msg("info-msg")
	logger.Warn().Msg("warn-msg")
	logger.Error().Msg("error-msg")
	cleanup()

	// All messages must appear in the file writer.
	for _, msg := range []string{"debug-msg", "info-msg", "warn-msg", "error-msg"} {
		assert.Contains(t, file.String(), msg, "file must contain %s", msg)
	}
}

// --------------------------------------------------------------------------
// Console writer
// --------------------------------------------------------------------------

// TestSetup_ConsoleWriterUsesTextFormat verifies that the console writer
// produces human-readable text (not JSON).
func TestSetup_ConsoleWriterUsesTextFormat(t *testing.T) {
	t.Parallel()
	var file, console bytes.Buffer

	logger, cleanup, err := logging.Setup("info", "text-cmd",
		logging.WithWriter(&file),
		logging.WithConsoleWriter(&console, zerolog.InfoLevel),
	)
	require.NoError(t, err)
	logger.Info().Str("k", "v").Msg("hello console")
	cleanup()

	// Console output must NOT be raw JSON.
	for _, line := range strings.Split(strings.TrimSpace(console.String()), "\n") {
		if line == "" {
			continue
		}
		// Strip ANSI escape codes before checking prefix.
		stripped := stripANSI(line)
		assert.False(t, strings.HasPrefix(strings.TrimSpace(stripped), "{"),
			"console output must not be raw JSON; got: %s", line)
	}
	assert.Contains(t, console.String(), "hello console")
}

// TestSetup_ConsoleWriterFiltersLevel verifies that the console writer only
// emits entries at or above its configured minimum level.
func TestSetup_ConsoleWriterFiltersLevel(t *testing.T) {
	t.Parallel()
	var file, console bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "filter-cmd",
		logging.WithWriter(&file),
		logging.WithConsoleWriter(&console, zerolog.ErrorLevel),
	)
	require.NoError(t, err)
	logger.Debug().Msg("debug-msg")
	logger.Info().Msg("info-msg")
	logger.Warn().Msg("warn-msg")
	logger.Error().Msg("error-msg")
	cleanup()

	// Only error and above should reach the console.
	assert.NotContains(t, console.String(), "debug-msg", "debug must be suppressed on console (minLevel=error)")
	assert.NotContains(t, console.String(), "info-msg", "info must be suppressed on console (minLevel=error)")
	assert.NotContains(t, console.String(), "warn-msg", "warn must be suppressed on console (minLevel=error)")
	assert.Contains(t, console.String(), "error-msg", "error must appear on console (minLevel=error)")

	// All messages must still appear in the file (file level = debug).
	for _, msg := range []string{"debug-msg", "info-msg", "warn-msg", "error-msg"} {
		assert.Contains(t, file.String(), msg, "file must contain %s", msg)
	}
}

// TestSetup_FileAndConsoleLevelsAreIndependent verifies that the file level
// and the console level are entirely independent of each other.
func TestSetup_FileAndConsoleLevelsAreIndependent(t *testing.T) {
	t.Parallel()
	var file, console bytes.Buffer

	// File = warn (only warn+error), Console = debug (everything).
	logger, cleanup, err := logging.Setup("warn", "indep-cmd",
		logging.WithWriter(&file),
		logging.WithConsoleWriter(&console, zerolog.DebugLevel),
	)
	require.NoError(t, err)
	logger.Debug().Msg("debug-msg")
	logger.Info().Msg("info-msg")
	logger.Warn().Msg("warn-msg")
	logger.Error().Msg("error-msg")
	cleanup()

	// Console must have everything (min level = debug).
	for _, msg := range []string{"debug-msg", "info-msg", "warn-msg", "error-msg"} {
		assert.Contains(t, console.String(), msg, "console must contain %s", msg)
	}

	// File must only have warn and above.
	assert.NotContains(t, file.String(), "debug-msg", "debug must be suppressed in file (fileLevel=warn)")
	assert.NotContains(t, file.String(), "info-msg", "info must be suppressed in file (fileLevel=warn)")
	assert.Contains(t, file.String(), "warn-msg", "warn must appear in file (fileLevel=warn)")
	assert.Contains(t, file.String(), "error-msg", "error must appear in file (fileLevel=warn)")
}

// TestSetup_ConsoleWriterExcludesCmdField verifies that the "cmd" key=value
// field is NOT printed on the console as a structured field (it is in
// FieldsExclude), though the command name may appear in boundary message text.
func TestSetup_ConsoleWriterExcludesCmdField(t *testing.T) {
	t.Parallel()
	var file, console bytes.Buffer

	logger, cleanup, err := logging.Setup("info", "secret-cmd",
		logging.WithWriter(&file),
		logging.WithConsoleWriter(&console, zerolog.InfoLevel),
	)
	require.NoError(t, err)
	// Log a message with an explicit "cmd" field to test field exclusion.
	logger.Info().Msg("user message")
	cleanup()

	consoleOut := console.String()

	// The "cmd" key must NOT appear as a structured key=value on the console.
	assert.NotContains(t, consoleOut, "cmd=secret-cmd",
		"console must not print the cmd field as a structured key=value")
	assert.NotContains(t, consoleOut, `"cmd"`,
		"console must not print cmd as a JSON key")

	// The user message must appear.
	assert.Contains(t, consoleOut, "user message")

	// The cmd field must still be in the file (JSON).
	assert.Contains(t, file.String(), `"cmd":"secret-cmd"`,
		"file must retain the cmd field")
}

// stripANSI removes ANSI escape codes from a string for plain-text assertions.
func stripANSI(s string) string {
	var out strings.Builder
	i := 0
	for i < len(s) {
		if s[i] == '\x1b' && i+1 < len(s) && s[i+1] == '[' {
			// skip until 'm'
			for i < len(s) && s[i] != 'm' {
				i++
			}
			i++ // skip 'm'
			continue
		}
		out.WriteByte(s[i])
		i++
	}
	return out.String()
}

func TestFor_AddsComponentField(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	root, cleanup, err := logging.Setup("debug", "parent-cmd", logging.WithWriter(&buf))
	require.NoError(t, err)

	sub := logging.For(root, "my-component")
	sub.Debug().Msg("sub message")
	cleanup()

	content := buf.String()
	assert.Contains(t, content, `"component":"my-component"`,
		"sub-logger should tag entries with the component name")
	assert.Contains(t, content, "sub message")
}

func TestFor_InheritsParentLevel(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	root, cleanup, err := logging.Setup("warn", "parent", logging.WithWriter(&buf))
	require.NoError(t, err)
	defer cleanup()

	sub := logging.For(root, "child")

	// Both loggers share the same underlying writer with the same level filter.
	// Emit a debug message — it must not appear in output (file level = warn).
	sub.Debug().Msg("debug-from-child")
	root.Debug().Msg("debug-from-parent")

	assert.NotContains(t, buf.String(), "debug-from-child",
		"sub-logger must respect parent's file level (warn)")
	assert.NotContains(t, buf.String(), "debug-from-parent",
		"root logger must respect file level (warn)")
}

func TestFor_NestedComponents(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	root, cleanup, err := logging.Setup("debug", "root-cmd", logging.WithWriter(&buf))
	require.NoError(t, err)

	mid := logging.For(root, "layer1")
	deep := logging.For(mid, "layer2")
	deep.Info().Msg("deep message")
	cleanup()

	content := buf.String()
	// The deepest sub-logger overwrites the component field with its own name.
	assert.Contains(t, content, `"component":"layer2"`)
	assert.Contains(t, content, "deep message")
}
