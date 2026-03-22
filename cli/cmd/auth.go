package cmd

import (
	"github.com/scylladb/argus/cli/internal/auth"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

var authCmd = &cobra.Command{
	Use:   "auth",
	Short: "Authenticate with Argus via Cloudflare Access",
	Long: `auth authenticates with Argus through Cloudflare Access.

On first use (or when the cached token has expired) cloudflared opens a
browser window so you can log in.  The resulting Cloudflare Access JWT is
stored in the system keychain (macOS Keychain, Windows Credential Manager,
or the Secret Service on Linux) and reused on subsequent invocations until
it expires.

The JWT is then exchanged for an Argus session token via POST /auth/login/cf
and that session is also stored in the keychain.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		cfg := ConfigFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "auth")

		// Ensure cloudflared is available (PATH → cache → download).
		log.Debug().Msg("locating cloudflared binary")
		cfSvc := services.NewCloudflaredService()
		binPath, err := cfSvc.Ensure(ctx)
		if err != nil {
			log.Error().Err(err).Msg("failed to locate cloudflared")
			return err
		}
		log.Debug().Str("bin", binPath).Msg("cloudflared binary ready")

		// ArgusService handles the full flow:
		//   1. Cache hit  → reuse keychain JWT, skip browser entirely.
		//   2. Cache miss → run `cloudflared access login` (opens browser),
		//                   parse JWT from output, cache it.
		//   3. Exchange JWT for Argus session, store in keychain.
		log.Info().Str("url", cfg.URL).Msg("authenticating with Argus")
		argusSvc := auth.NewArgusService(cfg.URL, binPath)
		if err := argusSvc.Login(ctx); err != nil {
			log.Error().Err(err).Msg("Argus login failed")
			return err
		}

		log.Info().Msg("authentication successful; session stored in keychain")
		return nil
	},
}

func init() {
	rootCmd.AddCommand(authCmd)
}
