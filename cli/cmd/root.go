package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/spf13/cobra"
)

// ErrInvalidURL is returned when the resolved Argus service URL is not a valid
// absolute URL.
var ErrInvalidURL = errors.New("cmd: invalid argus URL")

var (
	useText       bool
	useCloudflare bool
	argusURL      string
	cfgFile       string
	logLevel      string
	noCache       bool
	cacheTTL      string
)

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $XDG_CONFIG_HOME/argus-cli/config.yaml)")
	rootCmd.PersistentFlags().BoolVar(&useText, "text", false, "render output as a text table instead of JSON")
	rootCmd.PersistentFlags().StringVar(&argusURL, "url", "", "base URL of the Argus service (overrides config file)")
	rootCmd.PersistentFlags().BoolVar(&useCloudflare, "use-cloudflare", true, "Use cloudflare access (overrides config file)")
	rootCmd.PersistentFlags().StringVar(&logLevel, "log-level", "info", `log verbosity: trace, debug, info, warn, error`)
	rootCmd.PersistentFlags().BoolVar(&noCache, "no-cache", false, "bypass the local response cache; always fetch from the API")
	rootCmd.PersistentFlags().StringVar(&cacheTTL, "cache-ttl", "", "override the default cache TTL (e.g. 10m, 1h); ignored when --no-cache is set")
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
		var apiOpts []api.ClientOption
		if token, keychainErr := keychain.LoadPAT(); keychainErr == nil {
			apiOpts = append(apiOpts, api.WithAPIToken(token))
			logger.Debug().Msg("token loaded from keychain")
		} else if session, keychainErr := keychain.Load(); keychainErr == nil {
			apiOpts = append(apiOpts, api.WithSession(session))
			logger.Debug().Msg("session loaded from keychain")
		} else {
			logger.Debug().Err(keychainErr).Msg("no session or token in keychain")
		}

		if cfCookie, keychainErr := keychain.LoadCFToken(); keychainErr == nil && cfg.UseCf {
			apiOpts = append(apiOpts, api.WithCFToken(cfCookie))
			logger.Debug().Msg("loaded CF cookie from keychain")
		}

		if token := os.Getenv("ARGUS_TOKEN"); token != "" {
			apiOpts = append(apiOpts, api.WithAPIToken(token))
			logger.Debug().Msg("Using token from ARGUS_TOKEN")
		}

		if clientID := os.Getenv("ARGUS_CF_ACCESS_CLIENT_ID"); clientID != "" {
			clientSecret := os.Getenv("ARGUS_CF_ACCESS_CLIENT_SECRET")
			if clientSecret != "" {
				apiOpts = append(apiOpts, api.WithCFAccessSecret(clientID, clientSecret))
				logger.Debug().Msg("Using CF Service User from ARGUS_CF_ACCESS_CLIENT_*")
			}
		}

		client, err := api.New(cfg.URL, apiOpts...)
		if err != nil {
			return fmt.Errorf("%w %q: %w", ErrInvalidURL, cfg.URL, err)
		}

		ctx = contextWithAPIClient(ctx, client)

		cmd.SetContext(ctx)
		return nil
	},
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
