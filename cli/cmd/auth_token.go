package cmd

import (
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/spf13/cobra"
)

var authToken = &cobra.Command{
	Use:   "auth-token",
	Short: "Save argus token into keyring",
	Args:  cobra.MaximumNArgs(1),
	Long: `auth-token saves provides Argus PAT into OS keyring.

You probably want to use this for local and dev deployments as production deployments should use cloudflared login process via 'auth' command.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		cfg := ConfigFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "auth")
		if cfg.UseCf {
			log.Warn().Msg("cloudflare auth enabled; login with auth instead.")
		}
		if len(args) == 0 {
			log.Err(nil).Msg("Token not provided")
			return nil
		}
		tok := args[0]
		if err := keychain.StorePAT(tok); err != nil {
			return err
		}
		log.Info().Msg("saved token into keychain.")

		return nil
	},
}

func init() {
	rootCmd.AddCommand(authToken)
}
