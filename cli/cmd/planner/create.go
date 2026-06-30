package planner

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerCreate adds the "create" sub-command to parent.
func registerCreate(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "create",
		Short: "Create a release plan",
		Long: `Create a release plan from a JSON file and/or flags.

The plan can be described by a --file (the same schema 'get' emits by default)
and/or built up with flags; flags override matching fields from the file. Every
reference is by name (or, for tests, build_system_id) and resolved to a UUID
automatically — raw UUIDs are not accepted.

  # From an edited template (release-independent round-trip):
  argus planner create --file plan.json

  # From flags:
  argus planner create --release scylla-2026.2 --name "2026.2 Longevity" \
    --owner alice --assign tier1/longevity-200gb=bob \
    --assign tier2/longevity-100gb=$owner

Plan membership comes entirely from assignments: each entity is a test or group
(groups fan out to their enabled tests); use $owner to add a test without
assigning it to a specific participant. Tests not present in the target release
are reported and omitted, and the plan is created anyway.`,
		RunE: runCreate,
	}

	cmd.Flags().StringP("file", "f", "", "Plan spec JSON file (\"-\" for stdin)")
	cmd.Flags().StringP("release", "r", "", "Release name")
	cmd.Flags().String("name", "", "Plan name")
	cmd.Flags().String("description", "", "Plan description")
	cmd.Flags().String("owner", "", "Owner username")
	cmd.Flags().String("target-version", "", "Target version")
	cmd.Flags().String("view-id", "", "Existing view UUID to attach (optional)")
	cmd.Flags().StringArray("assign", nil, "Assignment as entity=username (use $owner to leave unassigned, repeatable)")

	parent.AddCommand(cmd)
}

// runCreate is the RunE handler for "planner create".
func runCreate(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "planner-create")

	tmpl, err := loadTemplate(cmd)
	if err != nil {
		return err
	}
	if err := overlayFlags(cmd, &tmpl); err != nil {
		return err
	}
	viewID, _ := cmd.Flags().GetString("view-id")

	svc := services.NewPlannerService(client, c)

	req, warnings, err := svc.BuildCreateRequest(ctx, tmpl)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Msg("failed to build create request")
		return err
	}
	req.ViewID = viewID

	plan, err := svc.CreatePlan(ctx, req)
	if err != nil {
		log.Error().Err(err).Msg("failed to create plan")
		return err
	}

	log.Info().Str("plan_id", plan.ID).Str("key", plan.Key).Msg("plan created successfully")
	return out.Write(models.NewKVTabular(plan))
}

// loadTemplate reads the --file plan spec (path or stdin) into a PlanTemplate.
// Returns a zero template when --file is not set.
func loadTemplate(cmd *cobra.Command) (models.PlanTemplate, error) {
	var tmpl models.PlanTemplate
	path, _ := cmd.Flags().GetString("file")
	if path == "" {
		return tmpl, nil
	}

	var raw []byte
	var err error
	if path == "-" {
		raw, err = io.ReadAll(bufio.NewReader(os.Stdin))
	} else {
		raw, err = os.ReadFile(path)
	}
	if err != nil {
		return tmpl, fmt.Errorf("reading plan file: %w", err)
	}
	if err := json.Unmarshal(raw, &tmpl); err != nil {
		return tmpl, fmt.Errorf("parsing plan file: %w", err)
	}
	return tmpl, nil
}

// overlayFlags applies command-line flags onto tmpl. Scalar flags override the
// file value only when explicitly set; --assign augments the file assignments.
func overlayFlags(cmd *cobra.Command, tmpl *models.PlanTemplate) error {
	if cmd.Flags().Changed("release") {
		tmpl.Release, _ = cmd.Flags().GetString("release")
	}
	if cmd.Flags().Changed("name") {
		tmpl.Name, _ = cmd.Flags().GetString("name")
	}
	if cmd.Flags().Changed("description") {
		tmpl.Description, _ = cmd.Flags().GetString("description")
	}
	if cmd.Flags().Changed("owner") {
		tmpl.Owner, _ = cmd.Flags().GetString("owner")
	}
	if cmd.Flags().Changed("target-version") {
		tmpl.TargetVersion, _ = cmd.Flags().GetString("target-version")
	}
	if cmd.Flags().Changed("assign") {
		assigns, _ := cmd.Flags().GetStringArray("assign")
		merged, err := parseAssignments(assigns, tmpl.Assignments)
		if err != nil {
			return err
		}
		tmpl.Assignments = merged
	}
	return nil
}

// parseAssignments parses repeatable "entity=username" flag values, merging
// them onto base (which may be nil). The entity key may contain "/" but not
// "=", so the first "=" separates entity from username.
func parseAssignments(raw []string, base map[string]string) (map[string]string, error) {
	out := map[string]string{}
	for k, v := range base {
		out[k] = v
	}
	for _, a := range raw {
		entity, user, ok := strings.Cut(a, "=")
		entity, user = strings.TrimSpace(entity), strings.TrimSpace(user)
		if !ok || entity == "" || user == "" {
			return nil, fmt.Errorf("invalid --assign %q: expected entity=username", a)
		}
		out[entity] = user
	}
	return out, nil
}
