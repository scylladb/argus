package view

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/gosimple/slug"
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
		Short: "Create a user view",
		Long: `Create a user view from a JSON file and/or flags.

The view is described by a --file (the same schema 'get' emits by default) and/or
built up with flags; flags override matching metadata fields from the file and
append to the file's items and widgets. Items and widget filters are
release-qualified build_system_id references (a single segment is a release,
"release/group" a group, and "release/group/test" a test) and are resolved to
UUIDs automatically.

  # From an edited template:
  argus view create --file view.json

  # Build entirely from flags (no file):
  argus view create --name "My Dashboard" \
    --item scylla-2026.2/tier1 \
    --item scylla-2026.2/tier1/longevity-100gb \
    --widget testDashboard --widget releaseStats

The --name value is the view's display name; its internal name (the URL slug
used to address the view) is derived from it automatically, e.g. "My Dashboard"
becomes "my-dashboard".

Widgets added with --widget are created with their default settings; run
'argus view widgets' to list the valid widget types. Items or filters that do
not resolve to an existing release/group/test are reported and omitted, and the
view is created anyway.

Note: a view cannot be linked to a plan at creation time (the API does not
accept plan_id on create); plan-backed views are created from the planner.`,
		RunE: runCreate,
	}

	cmd.Flags().StringP("file", "f", "", "View spec JSON file (\"-\" for stdin)")
	cmd.Flags().String("name", "", "View name; used as the display name, with a URL slug derived from it")
	cmd.Flags().String("description", "", "View description")
	cmd.Flags().StringArray("item", nil, "Item to add as a build_system_id reference (release, release/group, or release/group/test; repeatable)")
	cmd.Flags().StringArray("widget", nil, "Widget type to add with default settings (see 'argus view widgets'; repeatable)")

	parent.AddCommand(cmd)
}

// runCreate is the RunE handler for "view create".
func runCreate(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "view-create")

	tmpl, err := loadTemplate(cmd)
	if err != nil {
		return err
	}
	// Widgets from --file are user-authored, so reject unknown types up front.
	if err := validateWidgetTypes(tmpl.Widgets); err != nil {
		return err
	}
	overlayNameMeta(cmd, &tmpl)
	if err := overlayItemsAndWidgets(cmd, &tmpl); err != nil {
		return err
	}

	svc := services.NewViewService(client, c)

	req, warnings, err := svc.BuildCreateRequest(ctx, tmpl)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Msg("failed to build create request")
		return err
	}

	view, err := svc.CreateView(ctx, req)
	if err != nil {
		log.Error().Err(err).Msg("failed to create view")
		return err
	}

	log.Info().Str("view_id", view.ID).Str("name", view.Name).Msg("view created successfully")
	created, warnings, err := svc.ViewToTemplate(ctx, view)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Str("view_id", view.ID).Msg("failed to build view template")
		return err
	}
	return out.Write(models.NewKVTabular(created))
}

// loadTemplate reads the --file view spec (path or stdin) into a ViewTemplate.
// Returns a zero template when --file is not set.
func loadTemplate(cmd *cobra.Command) (models.ViewTemplate, error) {
	var tmpl models.ViewTemplate
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
		return tmpl, fmt.Errorf("reading view file: %w", err)
	}
	if err := json.Unmarshal(raw, &tmpl); err != nil {
		return tmpl, fmt.Errorf("parsing view file: %w", err)
	}
	return tmpl, nil
}

// overlayNameMeta applies the name/description metadata flags onto tmpl, shared
// by create and update. --name is the human display name; the view's internal
// name (its URL slug) is derived from it automatically, mirroring the dashboard
// editor. --description overrides the file/base value when set. When a base
// template (a --file spec or the current view) supplied a display name but no
// internal name, the slug is likewise derived so the view always has a name.
func overlayNameMeta(cmd *cobra.Command, tmpl *models.ViewTemplate) {
	if cmd.Flags().Changed("name") {
		name, _ := cmd.Flags().GetString("name")
		tmpl.DisplayName = name
		tmpl.Name = slug.Make(name)
	} else if tmpl.Name == "" && tmpl.DisplayName != "" {
		tmpl.Name = slug.Make(tmpl.DisplayName)
	}
	if cmd.Flags().Changed("description") {
		tmpl.Description, _ = cmd.Flags().GetString("description")
	}
}

// overlayItemsAndWidgets appends the repeatable --item and --widget flag values
// onto the template's items and widgets. Items are added verbatim as
// build_system_id references (resolved later); widgets are added with their
// type's default settings. An unknown --widget type is rejected here (the flag
// value is user-supplied), listing the valid types. Both append to whatever the
// file provided; final widget positions are assigned by the service when it
// builds the request.
func overlayItemsAndWidgets(cmd *cobra.Command, tmpl *models.ViewTemplate) error {
	if items, _ := cmd.Flags().GetStringArray("item"); len(items) > 0 {
		tmpl.Items = append(tmpl.Items, items...)
	}
	if widgets, _ := cmd.Flags().GetStringArray("widget"); len(widgets) > 0 {
		for _, wt := range widgets {
			if err := models.ValidateWidgetType(wt); err != nil {
				return err
			}
			tmpl.Widgets = append(tmpl.Widgets, models.NewWidgetWithDefaults(wt, 0))
		}
	}
	return nil
}

// validateWidgetTypes rejects any widget whose type this CLI does not recognise,
// listing the valid types. It guards user-supplied widgets (--file specs); it is
// deliberately not applied to widgets read back from a stored view.
func validateWidgetTypes(widgets []models.ViewWidget) error {
	for _, w := range widgets {
		if err := models.ValidateWidgetType(w.Type); err != nil {
			return err
		}
	}
	return nil
}
