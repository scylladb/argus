package logging_test

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

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
	var stderr bytes.Buffer

	_, cleanup, err := logging.Setup("info", "test-cmd",
		logging.WithCacheDir(cacheDir),
		logging.WithStderrWriter(&stderr),
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
	var stderr bytes.Buffer

	logger, cleanup, err := logging.Setup("info", "my-command",
		logging.WithCacheDir(cacheDir),
		logging.WithStderrWriter(&stderr),
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

func TestSetup_EmptyLevelDefaultsToInfo(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("", "cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	defer cleanup()

	// Debug messages should be suppressed at info level.
	assert.Equal(t, "info", logger.GetLevel().String())
}

func TestSetup_LevelCaseInsensitive(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("DEBUG", "cmd", logging.WithWriter(&buf))
	require.NoError(t, err)
	defer cleanup()

	assert.Equal(t, "debug", logger.GetLevel().String())
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
	var stderr bytes.Buffer

	// First invocation.
	_, cleanup1, err := logging.Setup("info", "first",
		logging.WithCacheDir(cacheDir),
		logging.WithStderrWriter(&stderr),
	)
	require.NoError(t, err)
	cleanup1()

	// Second invocation.
	_, cleanup2, err := logging.Setup("info", "second",
		logging.WithCacheDir(cacheDir),
		logging.WithStderrWriter(&stderr),
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

func TestSetup_LogFileIsHumanReadableText(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer

	logger, cleanup, err := logging.Setup("info", "readable", logging.WithWriter(&buf))
	require.NoError(t, err)
	logger.Info().Str("key", "value").Msg("check format")
	cleanup()

	content := buf.String()

	// Must NOT look like raw JSON (no leading '{').
	for _, line := range strings.Split(strings.TrimSpace(content), "\n") {
		if line == "" {
			continue
		}
		assert.False(t, strings.HasPrefix(strings.TrimSpace(line), "{"),
			"log lines must not be raw JSON; got: %s", line)
	}

	// Must contain the message and the extra field.
	assert.Contains(t, content, "check format")
	assert.Contains(t, content, "key=value")
}

// --------------------------------------------------------------------------
// Stderr fan-out
// --------------------------------------------------------------------------

// TestStderr_ErrorAppearsOnStderr verifies that an Error-level entry is
// written to the stderr writer in addition to the file writer.
func TestStderr_ErrorAppearsOnStderr(t *testing.T) {
	t.Parallel()
	var file, stderr bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "cmd",
		logging.WithWriter(&file),
		logging.WithStderrWriter(&stderr),
	)
	require.NoError(t, err)
	logger.Error().Msg("something went wrong")
	cleanup()

	assert.Contains(t, file.String(), "something went wrong", "file must contain the error")
	assert.Contains(t, stderr.String(), "something went wrong", "stderr must mirror the error")
}

// TestStderr_InfoDoesNotAppearOnStderr verifies that an Info-level entry is
// written to the file writer but NOT to stderr.
func TestStderr_InfoDoesNotAppearOnStderr(t *testing.T) {
	t.Parallel()
	var file, stderr bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "cmd",
		logging.WithWriter(&file),
		logging.WithStderrWriter(&stderr),
	)
	require.NoError(t, err)
	logger.Info().Msg("just informational")
	cleanup()

	assert.Contains(t, file.String(), "just informational", "file must contain the info entry")
	assert.NotContains(t, stderr.String(), "just informational", "stderr must not contain info entries")
}

// TestStderr_WarnDoesNotAppearOnStderr verifies that Warn is below the stderr
// threshold and stays file-only.
func TestStderr_WarnDoesNotAppearOnStderr(t *testing.T) {
	t.Parallel()
	var file, stderr bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "cmd",
		logging.WithWriter(&file),
		logging.WithStderrWriter(&stderr),
	)
	require.NoError(t, err)
	logger.Warn().Msg("just a warning")
	cleanup()

	assert.Contains(t, file.String(), "just a warning", "file must contain the warn entry")
	assert.NotContains(t, stderr.String(), "just a warning", "stderr must not contain warn entries")
}

// TestStderr_OnlyErrorsAndAboveReachStderr confirms the exact boundary:
// warn stays file-only, error crosses to stderr.
func TestStderr_OnlyErrorsAndAboveReachStderr(t *testing.T) {
	t.Parallel()
	var file, stderr bytes.Buffer

	logger, cleanup, err := logging.Setup("debug", "cmd",
		logging.WithWriter(&file),
		logging.WithStderrWriter(&stderr),
	)
	require.NoError(t, err)
	logger.Warn().Msg("warn-msg")
	logger.Error().Msg("error-msg")
	cleanup()

	// Both appear in the file.
	assert.Contains(t, file.String(), "warn-msg")
	assert.Contains(t, file.String(), "error-msg")

	// Only the error reaches stderr.
	assert.NotContains(t, stderr.String(), "warn-msg")
	assert.Contains(t, stderr.String(), "error-msg")
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
	assert.Contains(t, content, "component=my-component",
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
	assert.Equal(t, root.GetLevel(), sub.GetLevel(),
		"sub-logger must inherit the parent's log level")
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
	assert.Contains(t, content, "component=layer2")
	assert.Contains(t, content, "deep message")
}
