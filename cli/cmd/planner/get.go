package planner

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerGet adds the "get" sub-command to parent.
func registerGet(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "get",
		Short: "Show a single release plan",
		Long: `Show a single release plan addressed by its UUID or its
human-friendly "releaseName#planNumber" key, e.g.:
  argus planner get --plan-id scylla-2026.2#3
  argus planner get --plan-id 7f3c1e90-...`,
		RunE: runGet,
	}

	cmd.Flags().StringP("plan-id", "p", "", "Plan UUID or key (e.g. \"scylla-2026.2#3\") (required)")
	_ = cmd.MarkFlagRequired("plan-id")

	parent.AddCommand(cmd)
}

// runGet is the RunE handler for "planner get".
func runGet(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-get")

	planRef, _ := cmd.Flags().GetString("plan-id")
	log.Debug().Str("plan_id", planRef).Msg("fetching plan")

	svc := services.NewPlannerService(client, c)

	plan, err := svc.GetPlan(ctx, planRef)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to fetch plan")
		return err
	}

	log.Info().Str("plan_id", planRef).Msg("plan fetched successfully")
	return out.Write(models.NewKVTabular(plan))
}
