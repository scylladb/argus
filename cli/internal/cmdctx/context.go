// Package cmdctx defines the typed context keys and accessor functions used
// to propagate shared dependencies (API client, outputter, cache, logger,
// config, cleanup) through the cobra command tree.
//
// Both the top-level cmd package and sub-command packages (e.g. cmd/discussions)
// import this package to avoid circular dependencies.
package cmdctx

import (
	"context"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
)

// ---------------------------------------------------------------------------
// Outputter
// ---------------------------------------------------------------------------

type outputterKey struct{}

// WithOutputter returns a copy of ctx carrying out.
func WithOutputter(ctx context.Context, out output.Outputter) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, outputterKey{}, out)
}

// OutputterFrom retrieves the [output.Outputter] stored in ctx.
// It panics if no Outputter is present, which indicates that the command was
// registered without going through the root PersistentPreRun chain.
func OutputterFrom(ctx context.Context) output.Outputter {
	out, ok := ctx.Value(outputterKey{}).(output.Outputter)
	if !ok {
		panic("cmdctx: no output.Outputter in context; ensure PersistentPreRun propagates from root")
	}
	return out
}

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

type apiClientKey struct{}

// WithAPIClient returns a copy of ctx carrying client.
func WithAPIClient(ctx context.Context, client *api.Client) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, apiClientKey{}, client)
}

// APIClientFrom retrieves the [api.Client] stored in ctx.
// It panics if no client is present.
func APIClientFrom(ctx context.Context) *api.Client {
	client, ok := ctx.Value(apiClientKey{}).(*api.Client)
	if !ok {
		panic("cmdctx: no api.Client in context; ensure PersistentPreRun propagates from root")
	}
	return client
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

type configKey struct{}

// WithConfig returns a copy of ctx carrying cfg.
func WithConfig(ctx context.Context, cfg *config.Config) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, configKey{}, cfg)
}

// ConfigFrom retrieves the [config.Config] stored in ctx.
// It panics if no Config is present.
func ConfigFrom(ctx context.Context) *config.Config {
	cfg, ok := ctx.Value(configKey{}).(*config.Config)
	if !ok {
		panic("cmdctx: no config.Config in context; ensure PersistentPreRun propagates from root")
	}
	return cfg
}

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

type loggerKey struct{}

// WithLogger returns a copy of ctx carrying logger.
func WithLogger(ctx context.Context, logger zerolog.Logger) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, loggerKey{}, logger)
}

// LoggerFrom retrieves the [zerolog.Logger] stored in ctx.
// It panics if no logger is present.
func LoggerFrom(ctx context.Context) zerolog.Logger {
	logger, ok := ctx.Value(loggerKey{}).(zerolog.Logger)
	if !ok {
		panic("cmdctx: no zerolog.Logger in context; ensure PersistentPreRun propagates from root")
	}
	return logger
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

type cleanupKey struct{}

// WithCleanup returns a copy of ctx carrying cleanup.
func WithCleanup(ctx context.Context, cleanup logging.CleanupFunc) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, cleanupKey{}, cleanup)
}

// CleanupFrom retrieves the [logging.CleanupFunc] stored in ctx.
// Returns a no-op if none is present.
func CleanupFrom(ctx context.Context) logging.CleanupFunc {
	if fn, ok := ctx.Value(cleanupKey{}).(logging.CleanupFunc); ok {
		return fn
	}
	return func() {}
}

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------

type cacheKeyType struct{}

// WithCache returns a copy of ctx carrying c.
func WithCache(ctx context.Context, c *cache.Cache) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, cacheKeyType{}, c)
}

// CacheFrom retrieves the [cache.Cache] stored in ctx.
// Returns a disabled cache if none is present so callers never need to nil-check.
func CacheFrom(ctx context.Context) *cache.Cache {
	if c, ok := ctx.Value(cacheKeyType{}).(*cache.Cache); ok {
		return c
	}
	return cache.New("", cache.WithDisabled(true))
}
