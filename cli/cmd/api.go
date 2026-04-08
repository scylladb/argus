package cmd

import (
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
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
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)

		cacheKey := cache.VersionKey()
		if cached, _, err := cache.Get[models.Version](c, cacheKey); err == nil {
			return out.Write(cached)
		}

		req, err := client.NewRequest(ctx, "GET", api.ArgusVersion, nil)
		if err != nil {
			return err
		}
		mdl, err := api.DoJSON[models.Version](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, mdl, api.ArgusVersion, cache.TTLVersion)
		return out.Write(mdl)
	},
}

func init() {
	apiCmd.AddCommand(versionCmd)
	rootCmd.AddCommand(apiCmd)
}
