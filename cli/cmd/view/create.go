package view

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

// registerCreate adds the "create" sub-command to parent.
func registerCreate(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "create",
		Short: "Create a user view",
		Long: `Create a user view from a JSON file and/or flags.

The view is described by a --file (the same schema 'get' emits by default) and/or
built up with flags; flags override matching metadata fields from the file.
Items and widget filters are release-qualified build_system_id references
(a single segment is a release, "release/group" a group, and
"release/group/test" a test) and are resolved to UUIDs automatically.

  # From an edited template:
  argus view create --file view.json

  # Metadata-only from flags (empty view, no widgets):
  argus view create --name my-dashboard --display-name "My Dashboard"

Items or filters that do not resolve to an existing release/group/test are
reported and omitted, and the view is created anyway.`,
		RunE: runCreate,
	}

	cmd.Flags().StringP("file", "f", "", "View spec JSON file (\"-\" for stdin)")
	cmd.Flags().String("name", "", "View name (slug)")
	cmd.Flags().String("display-name", "", "View display name")
	cmd.Flags().String("description", "", "View description")

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
	overlayMetaFlags(cmd, &tmpl)

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

// overlayMetaFlags applies the metadata flags (--name/--display-name/
// --description) onto tmpl, overriding the file value only when explicitly set.
func overlayMetaFlags(cmd *cobra.Command, tmpl *models.ViewTemplate) {
	if cmd.Flags().Changed("name") {
		tmpl.Name, _ = cmd.Flags().GetString("name")
	}
	if cmd.Flags().Changed("display-name") {
		tmpl.DisplayName, _ = cmd.Flags().GetString("display-name")
	}
	if cmd.Flags().Changed("description") {
		tmpl.Description, _ = cmd.Flags().GetString("description")
	}
}
