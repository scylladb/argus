package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/auth"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// ErrInvalidURL is returned when the resolved Argus service URL is not a valid
// absolute URL.
var ErrInvalidURL = errors.New("cmd: invalid argus URL")

// ErrUnauthorized is returned (or wrapped) when a command fails due to an
// expired / missing credential and --non-interactive is set.
var ErrUnauthorized = errors.New("cmd: unauthorized")

var (
	useText        bool
	useCloudflare  bool
	argusURL       string
	cfgFile        string
	logLevel       string
	noCache        bool
	cacheTTL       string
	nonInteractive bool
)

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $XDG_CONFIG_HOME/argus-cli/config.yaml)")
	rootCmd.PersistentFlags().BoolVar(&useText, "text", false, "render output as a text table instead of JSON")
	rootCmd.PersistentFlags().StringVar(&argusURL, "url", "", "base URL of the Argus service (overrides config file)")
	rootCmd.PersistentFlags().BoolVar(&useCloudflare, "use-cloudflare", true, "Use cloudflare access (overrides config file)")
	rootCmd.PersistentFlags().StringVar(&logLevel, "log-level", "info", `log verbosity: trace, debug, info, warn, error`)
	rootCmd.PersistentFlags().BoolVar(&noCache, "no-cache", false, "bypass the local response cache; always fetch from the API")
	rootCmd.PersistentFlags().StringVar(&cacheTTL, "cache-ttl", "", "override the default cache TTL (e.g. 10m, 1h); ignored when --no-cache is set")
	rootCmd.PersistentFlags().BoolVar(&nonInteractive, "non-interactive", false, "disable interactive prompts; return an error instead of triggering re-authentication")
}

var rootCmd = &cobra.Command{
	Use:   "argus",
	Short: "Argus CLI",
	Long:  `Argus is a command-line interface for interacting with the Argus service.`,
	// PersistentPreRunE loads configuration, sets up logging, builds the
	// Outputter and API client, then stores all of them on the command context
	// so every sub-command has access without repeating flag parsing.
	PersistentPreRunE: func(cmd *cobra.Command, _ []string) error {
		// ---- logging -------------------------------------------------
		// Use the full command path (e.g. "argus auth") as the log tag so
		// every line is traceable back to the exact sub-command that ran.
		//
		// stderr is wired to the command's error writer so that cobra's own
		// error output and our logger both go to the same destination.
		logger, cleanup, err := logging.Setup(
			logLevel,
			cmd.CommandPath(),
			logging.WithStderrWriter(cmd.ErrOrStderr()),
		)
		if err != nil {
			return err
		}

		// Store the cleanup on the context so main.go can call it after
		// ExecuteContext returns — this guarantees the log file is flushed
		// and closed on both success and error paths.
		ctx := contextWithCleanup(cmd.Context(), cleanup)
		ctx = contextWithLogger(ctx, logger)

		// ---- non-interactive flag ------------------------------------
		ctx = contextWithNonInteractive(ctx, nonInteractive)

		// ---- output --------------------------------------------------
		out := output.New(cmd.OutOrStdout(), useText)
		ctx = contextWithOutputter(ctx, out)

		// ---- config --------------------------------------------------
		cfg, err := config.Load(cfgFile, cmd)
		if err != nil {
			logger.Error().Err(err).Msg("failed to load config")
			return err
		}
		logger.Debug().Str("url", cfg.URL).Msg("config loaded")

		ctx = contextWithConfig(ctx, cfg)

		// ---- cache ---------------------------------------------------
		cacheOpts := []cache.Option{
			cache.WithDisabled(noCache),
		}
		if cacheTTL != "" {
			if d, parseErr := time.ParseDuration(cacheTTL); parseErr == nil {
				cacheOpts = append(cacheOpts, cache.WithDefaultTTL(d))
			} else {
				logger.Warn().Str("cache_ttl", cacheTTL).Msg("ignoring invalid --cache-ttl value; expected a Go duration (e.g. 10m, 1h)")
			}
		}
		c := cache.New(config.CacheDir(), cacheOpts...)
		ctx = contextWithCache(ctx, c)
		logger.Debug().Bool("disabled", noCache).Str("dir", c.Dir()).Msg("cache initialised")
		go func() {
			if n := c.PurgeExpired(); n > 0 {
				logger.Debug().Int("removed", n).Msg("purged expired cache entries")
			}
		}()

		// ---- API client ----------------------------------------------
		client, buildErr := buildAPIClientRaw(cfg)
		if buildErr != nil {
			return buildErr
		}
		logger.Debug().Msg("API client built")

		ctx = contextWithAPIClient(ctx, client)

		cmd.SetContext(ctx)
		return nil
	},
}

// buildAPIClientRaw constructs an [api.Client] using credentials from the
// keychain and environment, applying them in priority order:
//
//  1. PAT from keychain
//  2. Session cookie from keychain
//  3. CF JWT from keychain (when CF is enabled)
//  4. ARGUS_TOKEN env var
//  5. CF Access service-account credentials from env
func buildAPIClientRaw(cfg *config.Config) (*api.Client, error) {
	var apiOpts []api.ClientOption
	if token, keychainErr := keychain.LoadPAT(); keychainErr == nil {
		apiOpts = append(apiOpts, api.WithAPIToken(token))
	} else if session, keychainErr := keychain.Load(); keychainErr == nil {
		apiOpts = append(apiOpts, api.WithSession(session))
	}

	if cfCookie, keychainErr := keychain.LoadCFToken(); keychainErr == nil && cfg.UseCf {
		apiOpts = append(apiOpts, api.WithCFToken(cfCookie))
	}

	if token := os.Getenv("ARGUS_TOKEN"); token != "" {
		apiOpts = append(apiOpts, api.WithAPIToken(token))
	}

	if clientID := os.Getenv("ARGUS_CF_ACCESS_CLIENT_ID"); clientID != "" {
		clientSecret := os.Getenv("ARGUS_CF_ACCESS_CLIENT_SECRET")
		if clientSecret != "" {
			apiOpts = append(apiOpts, api.WithCFAccessSecret(clientID, clientSecret))
		}
	}

	client, err := api.New(cfg.URL, apiOpts...)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrInvalidURL, cfg.URL, err)
	}
	return client, nil
}

// isUnauthorizedErr reports whether err looks like an unauthorized / expired
// session error returned by [api.DoJSON].
func isUnauthorizedErr(err error) bool {
	return err != nil && strings.HasPrefix(err.Error(), "unauthorized:")
}

// RunWithAuthRetry wraps fn so that if it returns an unauthorized error and
// the command context does not have --non-interactive set, it triggers the
// full login flow and retries fn once with a freshly built API client.
//
// Sub-commands that make API calls should wrap their logic with this helper:
//
//	RunE: func(cmd *cobra.Command, args []string) error {
//	    return RunWithAuthRetry(cmd, args, func(cmd *cobra.Command, args []string) error {
//	        // ... normal command logic ...
//	    })
//	},
func RunWithAuthRetry(cmd *cobra.Command, args []string, fn func(*cobra.Command, []string) error) error {
	err := fn(cmd, args)
	if err == nil {
		return nil
	}

	if !isUnauthorizedErr(err) {
		return err
	}

	ctx := cmd.Context()

	// --non-interactive: surface the error immediately without prompting.
	if NonInteractiveFrom(ctx) {
		return fmt.Errorf("%w: %w", ErrUnauthorized, err)
	}

	// Interactive retry: run the full login flow then rebuild the API client.
	cfg := ConfigFrom(ctx)
	log := LoggerFrom(ctx)
	log.Info().Msg("session expired; re-authenticating")

	if cfg.UseCf {
		cfSvc := services.NewCloudflaredService()
		binPath, cfErr := cfSvc.Ensure(ctx)
		if cfErr != nil {
			return fmt.Errorf("re-auth: locating cloudflared: %w", cfErr)
		}
		argusSvc := auth.NewArgusService(cfg.URL, binPath)
		if loginErr := argusSvc.Login(ctx); loginErr != nil {
			return fmt.Errorf("re-auth: login failed: %w", loginErr)
		}
	}

	// Rebuild client with fresh credentials.
	newClient, buildErr := buildAPIClientRaw(cfg)
	if buildErr != nil {
		return fmt.Errorf("re-auth: building client: %w", buildErr)
	}
	cmd.SetContext(contextWithAPIClient(ctx, newClient))

	log.Info().Msg("re-authentication successful; retrying command")
	return fn(cmd, args)
}

func ExecuteContext(ctx context.Context) error {
	rootCmd.SetOut(os.Stdout)
	rootCmd.SetErr(os.Stderr)

	err := rootCmd.ExecuteContext(ctx)

	// Flush and close the log file regardless of whether the command
	// succeeded or failed. CleanupFrom returns a no-op if logging setup
	// never ran (e.g. --help, unknown command, parse error).
	CleanupFrom(rootCmd.Context())()

	return err
}
