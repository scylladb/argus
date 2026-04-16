package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/rs/zerolog"
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

// SkipAuthRetryAnnotation is the cobra annotation key that, when present on a
// command, prevents [wrapAllCommandsWithAuthRetry] from wrapping that command's
// RunE with the transparent re-authentication logic.
//
// Commands that perform the authentication themselves (e.g. "auth",
// "auth-token") or that never touch the API (e.g. "cache clear") should carry
// this annotation.
const SkipAuthRetryAnnotation = "skipAuthRetry"

// ErrInvalidURL is returned when the resolved Argus service URL is not a valid
// absolute URL.
var ErrInvalidURL = errors.New("cmd: invalid argus URL")

// ErrUnauthorized is returned (or wrapped) when a command fails due to an
// expired / missing credential and --non-interactive is set.
var ErrUnauthorized = errors.New("cmd: unauthorized")

var (
	useText        bool
	useCloudflare  bool
	disableCf      bool
	argusURL       string
	cfgFile        string
	logLevel       string
	noCache        bool
	cacheTTL       string
	nonInteractive bool
	verbosity      int
)

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $XDG_CONFIG_HOME/argus-cli/config.yaml)")
	rootCmd.PersistentFlags().BoolVar(&useText, "text", false, "render output as a text table instead of JSON")
	rootCmd.PersistentFlags().StringVar(&argusURL, "url", "", "base URL of the Argus service (overrides config file)")
	rootCmd.PersistentFlags().BoolVar(&useCloudflare, "use-cloudflare", true, "Use cloudflare access (overrides config file)")
	rootCmd.PersistentFlags().BoolVar(&disableCf, "disable-cloudflare", false, "Disable all Cloudflare integration (cloudflared and CF headers/cookies)")
	rootCmd.PersistentFlags().StringVar(&logLevel, "log-level", "info", `log verbosity: trace, debug, info, warn, error`)
	rootCmd.PersistentFlags().BoolVar(&noCache, "no-cache", false, "bypass the local response cache; always fetch from the API")
	rootCmd.PersistentFlags().StringVar(&cacheTTL, "cache-ttl", "", "override the default cache TTL (e.g. 10m, 1h); ignored when --no-cache is set")
	rootCmd.PersistentFlags().BoolVar(&nonInteractive, "non-interactive", false, "disable interactive prompts; return an error instead of triggering re-authentication")
	rootCmd.PersistentFlags().CountVarP(&verbosity, "verbose", "v", "increase log verbosity: -v/-vv mirrors info logs to stderr, -vvv mirrors debug logs to stdout")
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
		// File log level is controlled by --log-level (default: info).
		// Console (stderr) is only active when -v flags are given:
		//   -v    → error level and above  → cmd.ErrOrStderr()
		//   -vv   → info level and above   → cmd.ErrOrStderr()
		//   -vvv  → debug level and above  → cmd.ErrOrStderr()
		// The two levels are independent: --log-level only affects the file.
		var logOpts []logging.Option
		switch {
		case verbosity >= 3:
			logOpts = append(logOpts, logging.WithConsoleWriter(
				cmd.ErrOrStderr(),
				zerolog.DebugLevel,
			))
		case verbosity == 2:
			logOpts = append(logOpts, logging.WithConsoleWriter(
				cmd.ErrOrStderr(),
				zerolog.InfoLevel,
			))
		case verbosity == 1:
			logOpts = append(logOpts, logging.WithConsoleWriter(
				cmd.ErrOrStderr(),
				zerolog.ErrorLevel,
			))
		}

		logger, cleanup, err := logging.Setup(
			logLevel,
			cmd.CommandPath(),
			logOpts...,
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
		if disableCf || envBoolTrue("ARGUS_DISABLE_CLOUDFLARE") {
			cfg.UseCf = false
			logger.Debug().Msg("cloudflare integration disabled via flag/env")
		}

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
		client, buildErr := buildAPIClientRaw(ctx, cfg)
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
// keychain and environment, applying them in priority order.
//
// When use_cloudflare is disabled (headless mode):
//
//  1. Headless CF Access credentials from keychain (stored by "auth headless")
//  2. ARGUS_AUTH_TOKEN env var
//  3. ARGUS_TOKEN env var
//  3. CF Access service-account credentials from env
//
// When use_cloudflare is enabled (cloudflared mode):
//
//  1. PAT from keychain
//  2. Session cookie from keychain
//  3. Cached Cloudflare Access JWT from cloudflared's local token cache
//  4. ARGUS_AUTH_TOKEN env var
//  5. ARGUS_TOKEN env var
//  5. CF Access service-account credentials from env
//
// The optional extraOpts are appended last, after all other options.
func buildAPIClientRaw(ctx context.Context, cfg *config.Config, extraOpts ...api.ClientOption) (*api.Client, error) {
	var apiOpts []api.ClientOption
	cfBypass := disableCf || envBoolTrue("ARGUS_DISABLE_CLOUDFLARE")

	if !cfg.UseCf && !cfBypass {
		// Headless mode: use CF Access service-token credentials from keychain.
		if cfID, cfSecret, argusToken, err := keychain.LoadCFAccess(); err == nil {
			apiOpts = append(apiOpts, api.WithCFAccessSecret(cfID, cfSecret))
			apiOpts = append(apiOpts, api.WithAPIToken(argusToken))
		}
	} else if cfg.UseCf && !cfBypass {
		// Cloudflared mode: use PAT or session from keychain.
		if token, err := keychain.LoadPAT(); err == nil {
			apiOpts = append(apiOpts, api.WithAPIToken(token))
		} else if session, err := keychain.Load(); err == nil {
			apiOpts = append(apiOpts, api.WithSession(session))
		}

		// Attach the cached Cloudflare Access JWT so requests pass through
		// the CF Access layer that sits in front of the Argus backend.
		// This is a best-effort read from cloudflared's local token cache
		// (~/.cloudflared/) — no network call or browser interaction.
		if cfToken, err := cachedCFToken(ctx, cfg.URL); err == nil {
			apiOpts = append(apiOpts, api.WithCFToken(cfToken))
		}
	}

	if token := os.Getenv("ARGUS_AUTH_TOKEN"); token != "" {
		apiOpts = append(apiOpts, api.WithAPIToken(token))
	} else if token := os.Getenv("ARGUS_TOKEN"); token != "" {
		apiOpts = append(apiOpts, api.WithAPIToken(token))
	}

	if !cfBypass {
		if clientID := os.Getenv("ARGUS_CF_ACCESS_CLIENT_ID"); clientID != "" {
			clientSecret := os.Getenv("ARGUS_CF_ACCESS_CLIENT_SECRET")
			if clientSecret != "" {
				apiOpts = append(apiOpts, api.WithCFAccessSecret(clientID, clientSecret))
			}
		}
	}

	apiOpts = append(apiOpts, extraOpts...)

	client, err := api.New(cfg.URL, apiOpts...)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrInvalidURL, cfg.URL, err)
	}
	return client, nil
}

func envBoolTrue(name string) bool {
	v := strings.TrimSpace(strings.ToLower(os.Getenv(name)))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

// cachedCFToken attempts to read a valid Cloudflare Access JWT from
// cloudflared's local token cache.  It locates the cloudflared binary (PATH
// or managed cache) and delegates to [auth.ArgusService.CachedCFToken].
//
// This is best-effort: if cloudflared is not installed, not on PATH, or the
// cached token is expired/missing, it returns an error and the caller should
// proceed without the CF token (the auth-retry mechanism will handle it).
func cachedCFToken(ctx context.Context, argusURL string) (string, error) {
	cfSvc := services.NewCloudflaredService()
	binPath, err := cfSvc.Ensure(ctx)
	if err != nil {
		return "", err
	}
	argusSvc := auth.NewArgusService(argusURL, binPath)
	return argusSvc.CachedCFToken(ctx)
}

// isUnauthorizedErr reports whether err is (or wraps) an unauthorized /
// expired-session error returned by [api.DoJSON].
func isUnauthorizedErr(err error) bool {
	return errors.Is(err, api.ErrUnauthorized)
}

// runWithAuthRetry wraps fn so that if it returns an unauthorized error and
// the command context does not have --non-interactive set, it triggers the
// full login flow and retries fn once with a freshly built API client.
func runWithAuthRetry(cmd *cobra.Command, args []string, fn func(*cobra.Command, []string) error) error {
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

	// Purge stale credentials from the keychain so the login flow does not
	// short-circuit on the same invalid PAT / CF token that just failed.
	_ = keychain.DeletePAT()
	_ = keychain.Delete()

	// When cloudflare is disabled the user is in headless mode — cloudflared
	// cannot help.  The user needs to update the headless credentials.
	if !cfg.UseCf {
		return fmt.Errorf(
			"re-auth: headless credentials are invalid or expired; " +
				"run `argus auth headless` to update them",
		)
	}

	cfSvc := services.NewCloudflaredService()
	binPath, cfErr := cfSvc.Ensure(ctx)
	if cfErr != nil {
		return fmt.Errorf("re-auth: locating cloudflared: %w", cfErr)
	}
	argusSvc := auth.NewArgusService(cfg.URL, binPath)
	if loginErr := argusSvc.Login(ctx); loginErr != nil {
		return fmt.Errorf("re-auth: login failed: %w", loginErr)
	}

	// Rebuild client with fresh credentials.
	newClient, buildErr := buildAPIClientRaw(ctx, cfg)
	if buildErr != nil {
		return fmt.Errorf("re-auth: building client: %w", buildErr)
	}
	cmd.SetContext(contextWithAPIClient(ctx, newClient))

	log.Info().Msg("re-authentication successful; retrying command")
	return fn(cmd, args)
}

// wrapAllCommandsWithAuthRetry recursively walks the command tree rooted at
// root and wraps every leaf command's RunE with [runWithAuthRetry] — unless the
// command carries the [SkipAuthRetryAnnotation].
//
// This is called once from [ExecuteContext] before execution starts, so every
// API-calling command gets transparent re-authentication for free without
// having to remember to wrap its RunE manually.
func wrapAllCommandsWithAuthRetry(root *cobra.Command) {
	for _, child := range root.Commands() {
		wrapAllCommandsWithAuthRetry(child) // recurse into sub-trees first

		if child.RunE == nil {
			continue
		}
		if _, skip := child.Annotations[SkipAuthRetryAnnotation]; skip {
			continue
		}
		orig := child.RunE
		child.RunE = func(cmd *cobra.Command, args []string) error {
			return runWithAuthRetry(cmd, args, orig)
		}
	}
}

func ExecuteContext(ctx context.Context) error {
	rootCmd.SetOut(os.Stdout)
	rootCmd.SetErr(os.Stderr)

	// Wrap every leaf command with transparent auth retry before execution.
	wrapAllCommandsWithAuthRetry(rootCmd)

	err := rootCmd.ExecuteContext(ctx)

	// Flush and close the log file regardless of whether the command
	// succeeded or failed. CleanupFrom returns a no-op if logging setup
	// never ran (e.g. --help, unknown command, parse error).
	CleanupFrom(rootCmd.Context())()

	return err
}
