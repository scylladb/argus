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
  argus planner get --plan-id 7f3c1e90-...

By default the plan is emitted as a release-independent, name-based template
(the same schema 'create --file' accepts) so it can be edited and re-created:
  argus planner get --plan-id scylla-2026.2#3 > plan.json

Use --resolved for a lossless, name-resolved view that keeps the plan's id, key
and status, or --raw for the unresolved JSON exactly as the backend returns it.`,
		RunE: runGet,
	}

	cmd.Flags().StringP("plan-id", "p", "", "Plan UUID or key (e.g. \"scylla-2026.2#3\") (required)")
	cmd.Flags().Bool("resolved", false, "Emit the full plan with references resolved to names (keeps id/key/status)")
	cmd.Flags().Bool("raw", false, "Emit the raw plan as returned by the API (UUIDs, unresolved)")
	cmd.MarkFlagsMutuallyExclusive("resolved", "raw")
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
	resolved, _ := cmd.Flags().GetBool("resolved")
	raw, _ := cmd.Flags().GetBool("raw")
	log.Debug().Str("plan_id", planRef).Bool("resolved", resolved).Bool("raw", raw).Msg("fetching plan")

	svc := services.NewPlannerService(client, c)

	plan, err := svc.GetPlan(ctx, planRef)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to fetch plan")
		return err
	}

	if raw {
		log.Info().Str("plan_id", planRef).Msg("plan fetched successfully (raw)")
		return out.Write(models.NewKVTabular(plan))
	}

	if resolved {
		log.Info().Str("plan_id", planRef).Msg("plan fetched successfully (resolved)")
		rp, err := svc.BuildResolvedPlan(ctx, plan)
		if err != nil {
			log.Error().Err(err).Str("plan_id", planRef).Msg("failed to resolve plan references")
			return err
		}
		return out.Write(rp)
	}

	tmpl, err := svc.BuildTemplate(ctx, plan)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to build plan template")
		return err
	}
	log.Info().Str("plan_id", planRef).Msg("plan template built successfully")
	return out.Write(models.NewKVTabular(tmpl))
}
