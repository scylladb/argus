package cmd

import (
	"context"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
)

// ---------------------------------------------------------------------------
// Thin wrappers that delegate to the shared cmdctx package.
//
// The unexported contextWith* functions are kept for backward compatibility
// with existing tests that export them via export_test.go.  New sub-command
// packages (e.g. cmd/discussions) should import cmdctx directly.
// ---------------------------------------------------------------------------

// contextWithOutputter returns a copy of ctx carrying out.
func contextWithOutputter(ctx context.Context, out output.Outputter) context.Context {
	return cmdctx.WithOutputter(ctx, out)
}

// OutputterFrom retrieves the [output.Outputter] stored in ctx.
func OutputterFrom(ctx context.Context) output.Outputter {
	return cmdctx.OutputterFrom(ctx)
}

// contextWithAPIClient returns a copy of ctx carrying client.
func contextWithAPIClient(ctx context.Context, client *api.Client) context.Context {
	return cmdctx.WithAPIClient(ctx, client)
}

// APIClientFrom retrieves the [api.Client] stored in ctx.
func APIClientFrom(ctx context.Context) *api.Client {
	return cmdctx.APIClientFrom(ctx)
}

// contextWithConfig returns a copy of ctx carrying cfg.
func contextWithConfig(ctx context.Context, cfg *config.Config) context.Context {
	return cmdctx.WithConfig(ctx, cfg)
}

// ConfigFrom retrieves the [config.Config] stored in ctx.
func ConfigFrom(ctx context.Context) *config.Config {
	return cmdctx.ConfigFrom(ctx)
}

// contextWithLogger returns a copy of ctx carrying logger.
func contextWithLogger(ctx context.Context, logger zerolog.Logger) context.Context {
	return cmdctx.WithLogger(ctx, logger)
}

// LoggerFrom retrieves the [zerolog.Logger] stored in ctx.
func LoggerFrom(ctx context.Context) zerolog.Logger {
	return cmdctx.LoggerFrom(ctx)
}

// contextWithCleanup returns a copy of ctx carrying cleanup.
func contextWithCleanup(ctx context.Context, cleanup logging.CleanupFunc) context.Context {
	return cmdctx.WithCleanup(ctx, cleanup)
}

// CleanupFrom retrieves the [logging.CleanupFunc] stored in ctx.
func CleanupFrom(ctx context.Context) logging.CleanupFunc {
	return cmdctx.CleanupFrom(ctx)
}

// contextWithCache returns a copy of ctx carrying c.
func contextWithCache(ctx context.Context, c *cache.Cache) context.Context {
	return cmdctx.WithCache(ctx, c)
}

// CacheFrom retrieves the [cache.Cache] stored in ctx.
func CacheFrom(ctx context.Context) *cache.Cache {
	return cmdctx.CacheFrom(ctx)
}
