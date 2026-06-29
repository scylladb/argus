package planner

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerOverview adds the "overview" sub-command to parent.
func registerOverview(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "overview",
		Short: "Overview a release's tests grouped by group",
		Long: `Show every enabled test in a release as a "group/test: build_system_id"
overview, useful for discovering the references that 'create'/'update' accept.

The release is referenced by its name (not a UUID), e.g.:
  argus planner overview --release scylla-2026.2`,
		RunE: runOverview,
	}

	cmd.Flags().StringP("release", "r", "", "Release name (required)")
	_ = cmd.MarkFlagRequired("release")

	parent.AddCommand(cmd)
}

// runOverview is the RunE handler for "planner overview".
func runOverview(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-overview")

	releaseRef, _ := cmd.Flags().GetString("release")
	log.Debug().Str("release", releaseRef).Msg("building release overview")

	svc := services.NewPlannerService(client, c)

	releaseID, err := svc.ResolveReleaseID(ctx, releaseRef)
	if err != nil {
		log.Error().Err(err).Str("release", releaseRef).Msg("failed to resolve release")
		return err
	}

	overview, err := svc.GetReleaseOverview(ctx, releaseID)
	if err != nil {
		log.Error().Err(err).Str("release", releaseRef).Msg("failed to build overview")
		return err
	}

	log.Info().Str("release", releaseRef).Int("count", len(overview)).Msg("overview built successfully")
	return out.Write(overview)
}
