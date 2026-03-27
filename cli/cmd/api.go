package cmd

import (
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

var apiCmd = &cobra.Command{
	Use:   "api",
	Short: "Group for generic api-related commands",
	Long:  ``,
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print API commit-id",
	Long:  ``,
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		req, err := client.NewRequest(ctx, "GET", api.ArgusVersion, nil)
		if err != nil {
			return err
		}
		mdl, err := api.DoJSON[models.Version](client, req)
		if err != nil {
			return err
		}
		out.Write(mdl)

		return nil
	},
}

func init() {
	apiCmd.AddCommand(versionCmd)
	rootCmd.AddCommand(apiCmd)
}
