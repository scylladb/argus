package cmd_test

import (
	"bytes"
	"context"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/cmd"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// LoggerFrom / contextWithLogger
// --------------------------------------------------------------------------

func TestContextWithLogger_RoundTrip(t *testing.T) {
	t.Parallel()

	logger := zerolog.New(&bytes.Buffer{}).With().Str("test", "yes").Logger()
	ctx := cmd.ContextWithLogger(context.Background(), logger)

	got := cmd.LoggerFrom(ctx)
	// zerolog.Logger is a value type; compare via its formatted output.
	assert.Equal(t, logger, got)
}

func TestContextWithLogger_NilContext(t *testing.T) {
	t.Parallel()

	logger := zerolog.Nop()
	// A nil ctx should not panic — it falls back to context.Background().
	ctx := cmd.ContextWithLogger(nil, logger) //nolint:staticcheck
	require.NotNil(t, ctx)
	_ = cmd.LoggerFrom(ctx) // must not panic
}

func TestLoggerFrom_PanicsWhenAbsent(t *testing.T) {
	t.Parallel()

	assert.Panics(t, func() {
		cmd.LoggerFrom(context.Background())
	})
}

// --------------------------------------------------------------------------
// ConfigFrom / contextWithConfig
// --------------------------------------------------------------------------

func TestContextWithConfig_RoundTrip(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{URL: "https://test.example.com"}
	ctx := cmd.ContextWithConfig(context.Background(), cfg)

	got := cmd.ConfigFrom(ctx)
	assert.Equal(t, cfg, got)
	assert.Equal(t, "https://test.example.com", got.URL)
}

func TestContextWithConfig_NilContext(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{}
	ctx := cmd.ContextWithConfig(nil, cfg) //nolint:staticcheck
	require.NotNil(t, ctx)
	_ = cmd.ConfigFrom(ctx)
}

func TestConfigFrom_PanicsWhenAbsent(t *testing.T) {
	t.Parallel()

	assert.Panics(t, func() {
		cmd.ConfigFrom(context.Background())
	})
}

// --------------------------------------------------------------------------
// APIClientFrom / contextWithAPIClient
// --------------------------------------------------------------------------

func TestContextWithAPIClient_RoundTrip(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	ctx := cmd.ContextWithAPIClient(context.Background(), client)
	got := cmd.APIClientFrom(ctx)
	assert.Equal(t, client, got)
}

func TestContextWithAPIClient_NilContext(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	ctx := cmd.ContextWithAPIClient(nil, client) //nolint:staticcheck
	require.NotNil(t, ctx)
	_ = cmd.APIClientFrom(ctx)
}

func TestAPIClientFrom_PanicsWhenAbsent(t *testing.T) {
	t.Parallel()

	assert.Panics(t, func() {
		cmd.APIClientFrom(context.Background())
	})
}

// --------------------------------------------------------------------------
// OutputterFrom / contextWithOutputter
// --------------------------------------------------------------------------

func TestContextWithOutputter_RoundTrip(t *testing.T) {
	t.Parallel()

	out := output.New(&bytes.Buffer{}, false)
	ctx := cmd.ContextWithOutputter(context.Background(), out)

	got := cmd.OutputterFrom(ctx)
	assert.Equal(t, out, got)
}

func TestContextWithOutputter_NilContext(t *testing.T) {
	t.Parallel()

	out := output.New(&bytes.Buffer{}, true)
	ctx := cmd.ContextWithOutputter(nil, out) //nolint:staticcheck
	require.NotNil(t, ctx)
	_ = cmd.OutputterFrom(ctx)
}

func TestOutputterFrom_PanicsWhenAbsent(t *testing.T) {
	t.Parallel()

	assert.Panics(t, func() {
		cmd.OutputterFrom(context.Background())
	})
}

// --------------------------------------------------------------------------
// CleanupFrom / contextWithCleanup
// --------------------------------------------------------------------------

func TestContextWithCleanup_RoundTrip(t *testing.T) {
	t.Parallel()

	called := false
	fn := logging.CleanupFunc(func() { called = true })

	ctx := cmd.ContextWithCleanup(context.Background(), fn)
	got := cmd.CleanupFrom(ctx)
	require.NotNil(t, got)

	got()
	assert.True(t, called, "cleanup function should have been called")
}

func TestContextWithCleanup_NilContext(t *testing.T) {
	t.Parallel()

	fn := logging.CleanupFunc(func() {})
	ctx := cmd.ContextWithCleanup(nil, fn) //nolint:staticcheck
	require.NotNil(t, ctx)
	_ = cmd.CleanupFrom(ctx)
}

func TestCleanupFrom_NoOpFallback(t *testing.T) {
	t.Parallel()

	// When no cleanup is stored, CleanupFrom must return a no-op (not panic).
	fn := cmd.CleanupFrom(context.Background())
	require.NotNil(t, fn)
	// Calling the no-op must not panic.
	assert.NotPanics(t, func() { fn() })
}
