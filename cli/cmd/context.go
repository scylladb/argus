package cmd

import (
	"context"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
)

// outputterKey is the context key used to store the [output.Outputter].
type outputterKey struct{}

// contextWithOutputter returns a copy of ctx carrying out.
func contextWithOutputter(ctx context.Context, out output.Outputter) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}

	return context.WithValue(ctx, outputterKey{}, out)
}

// OutputterFrom retrieves the [output.Outputter] stored in cmd's context.
// It panics if no Outputter is present, which indicates that the command was
// registered without going through the root PersistentPreRun chain.
func OutputterFrom(ctx context.Context) output.Outputter {
	out, ok := ctx.Value(outputterKey{}).(output.Outputter)
	if !ok {
		panic("cmd: no output.Outputter in context; ensure PersistentPreRun propagates from root")
	}

	return out
}

// apiClientKey is the context key used to store the [api.Client].
type apiClientKey struct{}

// contextWithAPIClient returns a copy of ctx carrying client.
func contextWithAPIClient(ctx context.Context, client *api.Client) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}

	return context.WithValue(ctx, apiClientKey{}, client)
}

// APIClientFrom retrieves the [api.Client] stored in cmd's context.
// It panics if no client is present, which indicates that the command was
// registered without going through the root PersistentPreRun chain.
func APIClientFrom(ctx context.Context) *api.Client {
	client, ok := ctx.Value(apiClientKey{}).(*api.Client)
	if !ok {
		panic("cmd: no api.Client in context; ensure PersistentPreRun propagates from root")
	}

	return client
}

// configKey is the context key used to store the [config.Config].
type configKey struct{}

// contextWithConfig returns a copy of ctx carrying cfg.
func contextWithConfig(ctx context.Context, cfg *config.Config) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}

	return context.WithValue(ctx, configKey{}, cfg)
}

// ConfigFrom retrieves the [config.Config] stored in cmd's context.
// It panics if no Config is present, which indicates that the command was
// registered without going through the root PersistentPreRun chain.
func ConfigFrom(ctx context.Context) *config.Config {
	cfg, ok := ctx.Value(configKey{}).(*config.Config)
	if !ok {
		panic("cmd: no config.Config in context; ensure PersistentPreRun propagates from root")
	}

	return cfg
}

// loggerKey is the context key used to store the root [zerolog.Logger].
type loggerKey struct{}

// contextWithLogger returns a copy of ctx carrying logger.
func contextWithLogger(ctx context.Context, logger zerolog.Logger) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}

	return context.WithValue(ctx, loggerKey{}, logger)
}

// LoggerFrom retrieves the [zerolog.Logger] stored in ctx.
// It panics if no logger is present, which indicates that the command was
// registered without going through the root PersistentPreRun chain.
func LoggerFrom(ctx context.Context) zerolog.Logger {
	logger, ok := ctx.Value(loggerKey{}).(zerolog.Logger)
	if !ok {
		panic("cmd: no zerolog.Logger in context; ensure PersistentPreRun propagates from root")
	}

	return logger
}

// cleanupKey is the context key used to store the logging [logging.CleanupFunc].
type cleanupKey struct{}

// contextWithCleanup returns a copy of ctx carrying cleanup.
func contextWithCleanup(ctx context.Context, cleanup logging.CleanupFunc) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}

	return context.WithValue(ctx, cleanupKey{}, cleanup)
}

// CleanupFrom retrieves the [logging.CleanupFunc] stored in ctx.
// Returns a no-op if none is present (e.g. when logging setup failed or in
// tests that bypass PersistentPreRun).
func CleanupFrom(ctx context.Context) logging.CleanupFunc {
	if fn, ok := ctx.Value(cleanupKey{}).(logging.CleanupFunc); ok {
		return fn
	}
	return func() {}
}
