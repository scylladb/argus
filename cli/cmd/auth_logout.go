package cmd

import (
	"fmt"

	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/spf13/cobra"
)

var authLogoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Remove all stored authentication credentials from the system keychain",
	Long: `auth logout removes every credential the Argus CLI has stored in the
system keychain:

  - Argus API token (PAT)
  - Argus session cookie
  - Headless CF Access credentials (client ID, client secret, Argus token)

After running this command you will need to re-authenticate via
"argus auth" or "argus auth headless" before running any API commands.`,
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "auth")

		var errs []error

		if err := keychain.DeletePAT(); err != nil {
			log.Warn().Err(err).Msg("failed to delete PAT")
			errs = append(errs, err)
		}

		if err := keychain.Delete(); err != nil {
			log.Warn().Err(err).Msg("failed to delete session")
			errs = append(errs, err)
		}

		if err := keychain.DeleteCFAccess(); err != nil {
			log.Warn().Err(err).Msg("failed to delete headless CF Access credentials")
			errs = append(errs, err)
		}

		if len(errs) > 0 {
			return fmt.Errorf("some credentials could not be removed; check warnings above")
		}

		log.Info().Msg("all credentials removed from keychain")
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), "Logged out — all stored credentials have been removed.")
		return nil
	},
}

func init() {
	authCmd.AddCommand(authLogoutCmd)
}
