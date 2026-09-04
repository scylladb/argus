package cmd

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/auth"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

var authCmd = &cobra.Command{
	Use:   "auth",
	Short: "Authenticate with Argus via Cloudflare Access",
	Long: `auth authenticates with Argus through Cloudflare Access.

If valid credentials already exist in the keychain the command verifies
them with a lightweight API call and exits early.  Only when the existing
credentials are missing or rejected does the command proceed with the full
cloudflared browser-based login flow.

On first use (or when the cached token has expired) cloudflared opens a
browser window so you can log in.  The resulting Cloudflare Access JWT is
stored in the system keychain (macOS Keychain, Windows Credential Manager,
or the Secret Service on Linux) and reused on subsequent invocations until
it expires.

The JWT is then exchanged for an Argus session via POST /auth/login/cf and
the session for a durable API token (PAT) stored in the keychain.  A PAT that
is already stored is kept unless Argus rejected it: Argus stores only a digest
of each token, so requesting one always issues a new token and invalidates
the previous one for every other client.`,
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		cfg := ConfigFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "auth")

		// ---- verify existing credentials --------------------------------
		// GET /api/v1/users is read-only. GET /api/v1/user/token must not be
		// used here: it issues a new token, invalidating the stored PAT.
		var verifyErr error
		client := APIClientFrom(ctx)
		if client != nil {
			log.Debug().Msg("verifying existing credentials")
			req, reqErr := client.NewRequest(ctx, http.MethodGet, api.Users, nil)
			if reqErr == nil {
				if _, verifyErr = api.DoJSON[models.UsersMap](client, req); verifyErr == nil {
					log.Info().Msg("existing credentials are valid")
					_, _ = fmt.Fprintln(cmd.OutOrStdout(), "Already authenticated.")
					return nil
				}
			}
			log.Debug().Err(verifyErr).Msg("existing credentials invalid or missing; proceeding with login")
		}

		// ---- headless mode: cloudflare disabled -------------------------
		if !cfg.UseCf {
			return fmt.Errorf(
				"cloudflare access is disabled (use_cloudflare=false); " +
					"run `argus auth headless` to update headless credentials, " +
					"or `argus config set use_cloudflare true` to switch to cloudflared login",
			)
		}

		// ---- cloudflared login flow -------------------------------------
		// Login() keeps a stored PAT (fetching a new one rotates it
		// server-side). Purge it only when Argus itself rejected it; a
		// Cloudflare challenge or a missing CF token says nothing about the PAT.
		if verifyErr != nil && errors.Is(verifyErr, api.ErrUnauthorized) && !errors.Is(verifyErr, api.ErrCFChallenge) {
			log.Debug().Msg("stored PAT rejected by Argus; discarding it")
			_ = keychain.DeletePAT()
		}
		_ = keychain.Delete()

		log.Debug().Msg("locating cloudflared binary")
		cfSvc := services.NewCloudflaredService()
		binPath, err := cfSvc.Ensure(ctx)
		if err != nil {
			log.Error().Err(err).Msg("failed to locate cloudflared")
			return err
		}
		log.Debug().Str("bin", binPath).Msg("cloudflared binary ready")

		log.Info().Str("url", cfg.URL).Msg("authenticating with Argus")
		argusSvc := auth.NewArgusService(cfg.URL, binPath)
		if err := argusSvc.Login(ctx); err != nil {
			log.Error().Err(err).Msg("Argus login failed")
			return err
		}

		log.Info().Msg("authentication successful; credentials stored in keychain")
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "Authentication successful.")

		return nil
	},
}

func init() {
	rootCmd.AddCommand(authCmd)
}
