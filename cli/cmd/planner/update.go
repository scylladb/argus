package planner

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerUpdate adds the "update" sub-command to parent.
func registerUpdate(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "update",
		Short: "Update a release plan via a computed diff",
		Long: `Update a release plan, sending only the fields that changed.

The plan is addressed by its UUID or "releaseName#planNumber" key. Changes can
come from a --file diff (the schema below) and/or from flags; flags override
matching scalars in the file and augment its collections. Every reference is by
name (or, for tests, build_system_id) and resolved to a UUID automatically —
raw UUIDs are not accepted.

  # Rename only (sends just the name scalar):
  argus planner update --plan-id scylla-2026.2#3 --name "2026.2 Longevity (GA)"

  # Add a test, drop a stored group, (re)assign an entity:
  argus planner update --plan-id scylla-2026.2#3 \
    --add-test scylla-2026.2/tier1/longevity-200gb \
    --remove-group tier2 \
    --assign scylla-2026.2/tier1/longevity-200gb=bob

  # From a JSON diff file (or stdin with '-'):
  argus planner update --plan-id scylla-2026.2#3 --file edit.json

Groups passed to --add-group are expanded to their enabled tests (no group is
stored); a group assignment fans out to each of those tests. Tests referenced
for add/remove that do not exist in the release are reported and skipped.`,
		RunE: runUpdate,
	}

	cmd.Flags().StringP("plan-id", "p", "", "Plan UUID or key (required)")
	cmd.Flags().StringP("file", "f", "", "Diff spec JSON file (\"-\" for stdin)")
	cmd.Flags().String("name", "", "New plan name")
	cmd.Flags().String("description", "", "New description")
	cmd.Flags().String("owner", "", "New owner username")
	cmd.Flags().String("target-version", "", "New target version")
	cmd.Flags().Bool("completed", false, "Mark the plan completed")
	cmd.Flags().StringArray("add-test", nil, "Add test by build_system_id or group/test (repeatable)")
	cmd.Flags().StringArray("remove-test", nil, "Remove test by build_system_id or group/test (repeatable)")
	cmd.Flags().StringArray("add-group", nil, "Add group, expanded to its enabled tests (repeatable)")
	cmd.Flags().StringArray("remove-group", nil, "Remove a stored group by name (repeatable)")
	cmd.Flags().StringArray("add-participant", nil, "Add participant username (repeatable)")
	cmd.Flags().StringArray("remove-participant", nil, "Remove participant username (repeatable)")
	cmd.Flags().StringArray("assign", nil, "Assignment as entity=username (repeatable)")
	cmd.Flags().StringArray("unassign", nil, "Remove assignment for entity (repeatable)")
	_ = cmd.MarkFlagRequired("plan-id")

	parent.AddCommand(cmd)
}

// runUpdate is the RunE handler for "planner update".
func runUpdate(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-update")

	planRef, _ := cmd.Flags().GetString("plan-id")

	spec, err := loadUpdateSpec(cmd)
	if err != nil {
		return err
	}
	if err := overlayUpdateFlags(cmd, &spec); err != nil {
		return err
	}

	svc := services.NewPlannerService(client, c)

	// Fetch the current plan to obtain its UUID id and release for resolution.
	plan, err := svc.GetPlan(ctx, planRef)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to fetch plan")
		return err
	}

	diff, warnings, err := svc.BuildUpdateRequest(ctx, plan, spec)
	if err != nil {
		log.Error().Err(err).Msg("failed to build update diff")
		return err
	}
	for _, w := range warnings {
		log.Warn().Msg(w)
	}

	if err := svc.UpdatePlan(ctx, diff); err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to update plan")
		return err
	}
	log.Info().Str("plan_id", planRef).Msg("plan updated successfully")

	// Re-fetch and show the resolved, updated plan.
	updated, err := svc.GetPlan(ctx, planRef)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to fetch updated plan")
		return err
	}
	resolved, err := svc.BuildResolvedPlan(ctx, updated)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planRef).Msg("failed to resolve updated plan")
		return err
	}
	return out.Write(resolved)
}

// loadUpdateSpec reads the --file diff spec (path or stdin) into a
// PlanUpdateSpec. Returns a zero spec when --file is not set.
func loadUpdateSpec(cmd *cobra.Command) (spec models.PlanUpdateSpec, err error) {
	path, _ := cmd.Flags().GetString("file")
	if path == "" {
		return spec, nil
	}

	var raw []byte
	if path == "-" {
		raw, err = io.ReadAll(bufio.NewReader(os.Stdin))
	} else {
		raw, err = os.ReadFile(path)
	}
	if err != nil {
		return spec, fmt.Errorf("reading diff file: %w", err)
	}
	if err := json.Unmarshal(raw, &spec); err != nil {
		return spec, fmt.Errorf("parsing diff file: %w", err)
	}
	return spec, nil
}

// overlayUpdateFlags applies command-line flags onto spec. Scalar flags
// override the file value only when explicitly set; list/map flags augment the
// corresponding file collections.
func overlayUpdateFlags(cmd *cobra.Command, spec *models.PlanUpdateSpec) error {
	setStr := func(flag string, dst **string) {
		if cmd.Flags().Changed(flag) {
			v, _ := cmd.Flags().GetString(flag)
			*dst = &v
		}
	}
	setStr("name", &spec.Name)
	setStr("description", &spec.Description)
	setStr("owner", &spec.Owner)
	setStr("target-version", &spec.TargetVersion)
	if cmd.Flags().Changed("completed") {
		v, _ := cmd.Flags().GetBool("completed")
		spec.Completed = &v
	}

	appendArr := func(flag string, dst *[]string) {
		if cmd.Flags().Changed(flag) {
			v, _ := cmd.Flags().GetStringArray(flag)
			*dst = append(*dst, v...)
		}
	}
	appendArr("add-test", &spec.TestsAdd)
	appendArr("remove-test", &spec.TestsRemove)
	appendArr("add-group", &spec.GroupsAdd)
	appendArr("remove-group", &spec.GroupsRemove)
	appendArr("add-participant", &spec.ParticipantsAdd)
	appendArr("remove-participant", &spec.ParticipantsRemove)
	appendArr("unassign", &spec.AssigneeMappingRemove)

	if cmd.Flags().Changed("assign") {
		assigns, _ := cmd.Flags().GetStringArray("assign")
		merged, err := parseAssignments(assigns, spec.AssigneeMappingSet)
		if err != nil {
			return err
		}
		spec.AssigneeMappingSet = merged
	}
	return nil
}
