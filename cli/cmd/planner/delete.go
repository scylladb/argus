package planner

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerDelete adds the "delete" sub-command to parent.
func registerDelete(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "delete",
		Short: "Delete a release plan",
		Long: `Delete a release plan addressed by its UUID or "releaseName#planNumber" key.

By default the plan's associated view is deleted as well; pass --no-delete-view
to detach and keep it. A confirmation prompt is shown unless --yes is given.

  argus planner delete --plan-id scylla-2026.2#3 --yes
  argus planner delete --plan-id 7f3c1e90-... --no-delete-view --yes`,
		RunE: runDelete,
	}

	cmd.Flags().StringP("plan-id", "p", "", "Plan UUID or key (required)")
	cmd.Flags().Bool("no-delete-view", false, "Keep the plan's associated view (default is to delete it)")
	cmd.Flags().Bool("yes", false, "Skip the confirmation prompt")
	_ = cmd.MarkFlagRequired("plan-id")

	parent.AddCommand(cmd)
}

// runDelete is the RunE handler for "planner delete".
func runDelete(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-delete")

	planRef, _ := cmd.Flags().GetString("plan-id")
	noDeleteView, _ := cmd.Flags().GetBool("no-delete-view")
	deleteView := !noDeleteView
	yes, _ := cmd.Flags().GetBool("yes")

	svc := services.NewPlannerService(client, c)

	plan, err := svc.GetPlan(ctx, planRef)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to fetch plan")
		return err
	}
	summaries, err := svc.BuildPlanSummaries(ctx, models.ReleasePlanList{plan})
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to summarize plan")
		return err
	}
	if err := out.Write(summaries[0]); err != nil {
		return err
	}

	if !yes {
		ok, err := confirm(cmd, fmt.Sprintf("Delete plan %q?", planRef))
		if err != nil {
			return err
		}
		if !ok {
			log.Info().Str("plan_id", planRef).Msg("deletion aborted by user")
			return out.Write(map[string]string{"status": "aborted", "plan_id": planRef})
		}
	}

	if err := svc.DeletePlan(ctx, planRef, deleteView); err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to delete plan")
		return err
	}

	log.Info().Str("plan_id", planRef).Bool("delete_view", deleteView).Msg("plan deleted successfully")
	return out.Write(map[string]string{"status": "deleted", "plan_id": planRef})
}

// confirm prints prompt to stderr and reads a y/N answer from stdin.
func confirm(cmd *cobra.Command, prompt string) (bool, error) {
	fmt.Fprintf(os.Stderr, "%s [y/N]: ", prompt)
	scanner := bufio.NewScanner(os.Stdin)
	if !scanner.Scan() {
		if err := scanner.Err(); err != nil {
			return false, fmt.Errorf("reading confirmation: %w", err)
		}
		return false, nil
	}
	answer := strings.ToLower(strings.TrimSpace(scanner.Text()))
	return answer == "y" || answer == "yes", nil
}
