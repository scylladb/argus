package planner

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
		Short: "List release plans for a release",
		Long: `List the release plans belonging to a release.

The release is referenced by its name (not a UUID), e.g.:
  argus planner list --release scylla-2026.2`,
		RunE: runList,
	}

	cmd.Flags().StringP("release", "r", "", "Release name (required)")
	_ = cmd.MarkFlagRequired("release")

	parent.AddCommand(cmd)
}

// runList is the RunE handler for "planner list".
func runList(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-list")

	releaseRef, _ := cmd.Flags().GetString("release")
	log.Debug().Str("release", releaseRef).Msg("listing plans for release")

	svc := services.NewPlannerService(client, c)

	releaseID, err := svc.ResolveReleaseID(ctx, releaseRef)
	if err != nil {
		log.Error().Err(err).Str("release", releaseRef).Msg("failed to resolve release")
		return err
	}

	plans, err := svc.GetPlansForRelease(ctx, releaseID)
	if err != nil {
		log.Error().Err(err).Str("release", releaseRef).Msg("failed to list plans")
		return err
	}

	log.Info().Str("release", releaseRef).Int("count", len(plans)).Msg("plans listed successfully")
	return out.Write(models.NewTabularSlice(plans))
}
