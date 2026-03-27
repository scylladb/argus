package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"

	"github.com/scylladb/argus/cli/internal/api"
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
)

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $XDG_CONFIG_HOME/argus-cli/config.yaml)")
	rootCmd.PersistentFlags().BoolVar(&useText, "text", false, "render output as a text table instead of JSON")
	rootCmd.PersistentFlags().StringVar(&argusURL, "url", "", "base URL of the Argus service (overrides config file)")
	rootCmd.PersistentFlags().BoolVar(&useCloudflare, "use-cloudflare", true, "Use cloudflare access (overrides config file)")
	rootCmd.PersistentFlags().StringVar(&logLevel, "log-level", "info", `log verbosity: trace, debug, info, warn, error`)
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

		if token := os.Getenv("ARGUS_TOKEN"); token != "" {
			apiOpts = append(apiOpts, api.WithAPIToken(token))
			logger.Debug().Msg("Using token from ARGUS_TOKEN")
		}

		if clientId := os.Getenv("ARGUS_CF_ACCESS_CLIENT_ID"); clientId != "" {
			clientSecret := os.Getenv("ARGUS_CF_ACCESS_CLIENT_SECRET")
			if clientSecret != "" {
				apiOpts = append(apiOpts, api.WithCFAccessSecret(clientId, clientSecret))
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
