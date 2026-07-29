package view

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerList adds the "list" sub-command to parent.
func registerList(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List user views",
		Long: `List Argus user views.

By default every view is listed; pass --user to scope the list to a single
owner (by username), e.g.:
  argus view list
  argus view list --user alice`,
		RunE: runList,
	}

	cmd.Flags().StringP("user", "u", "", "Owner username to filter by (optional)")
	cmd.Flags().Bool("raw", false, "Emit raw views as returned by the API (UUIDs, unresolved)")

	parent.AddCommand(cmd)
}

// runList is the RunE handler for "view list".
func runList(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "view-list")

	userRef, _ := cmd.Flags().GetString("user")
	raw, _ := cmd.Flags().GetBool("raw")
	log.Debug().Str("user", userRef).Bool("raw", raw).Msg("listing views")

	svc := services.NewViewService(client, c)

	views, err := svc.ListViews(ctx, userRef)
	if err != nil {
		log.Error().Err(err).Msg("failed to list views")
		return err
	}

	log.Info().Int("count", len(views)).Msg("views listed successfully")
	if raw {
		return out.Write(models.NewTabularSlice(views))
	}
	summaries, err := svc.BuildSummaries(ctx, views)
	if err != nil {
		log.Error().Err(err).Msg("failed to summarize views")
		return err
	}
	return out.Write(models.ViewSummaries(summaries))
}
