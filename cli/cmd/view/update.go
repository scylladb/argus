package view

import (
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
		Short: "Update a user view",
		Long: `Update a user view. The update is a full replacement of the view's items and
widgets, so metadata-only edits start from the view's current state.

The view is addressed by its UUID or name. Provide a --file to replace the
view's items and widgets wholesale (the schema 'get' emits); without --file the
current view is used as the base so --name/--display-name/--description edit just
the metadata while preserving items and widgets. Flags override matching
metadata fields from the file. References resolve as for 'create'.

  # Rename only (items and widgets preserved):
  argus view update --view my-dashboard --display-name "My Dashboard (2026.2)"

  # Replace items/widgets from an edited template:
  argus view update --view my-dashboard --file view.json

A plan-backed view keeps its plan link (plan_id is never sent). Items or filters
that do not resolve are reported and omitted.`,
		RunE: runUpdate,
	}

	cmd.Flags().StringP("view", "i", "", "View UUID or name (required)")
	cmd.Flags().StringP("file", "f", "", "View spec JSON file (\"-\" for stdin); replaces items and widgets")
	cmd.Flags().String("name", "", "New view name (slug)")
	cmd.Flags().String("display-name", "", "New display name")
	cmd.Flags().String("description", "", "New description")
	_ = cmd.MarkFlagRequired("view")

	parent.AddCommand(cmd)
}

// runUpdate is the RunE handler for "view update".
func runUpdate(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "view-update")

	viewRef, _ := cmd.Flags().GetString("view")

	svc := services.NewViewService(client, c)

	// Fetch the current view for its canonical UUID and, when no --file is
	// given, as the base template so a metadata-only edit preserves items/widgets.
	view, err := svc.GetView(ctx, viewRef)
	if err != nil {
		log.Error().Err(err).Str("view", viewRef).Msg("failed to fetch view")
		return err
	}

	var tmpl models.ViewTemplate
	if cmd.Flags().Changed("file") {
		tmpl, err = loadTemplate(cmd)
		if err != nil {
			return err
		}
	} else {
		var warnings []string
		tmpl, warnings, err = svc.ViewToTemplate(ctx, view)
		for _, w := range warnings {
			log.Warn().Msg(w)
		}
		if err != nil {
			log.Error().Err(err).Str("view", viewRef).Msg("failed to build base template")
			return err
		}
	}
	overlayMetaFlags(cmd, &tmpl)

	req, warnings, err := svc.BuildUpdateRequest(ctx, view.ID, tmpl)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Msg("failed to build update request")
		return err
	}

	if err := svc.UpdateView(ctx, req); err != nil {
		log.Error().Err(err).Str("view_id", view.ID).Msg("failed to update view")
		return err
	}
	log.Info().Str("view_id", view.ID).Msg("view updated successfully")

	// Re-fetch and show the updated view in the same template format as 'get'.
	updated, err := svc.GetView(ctx, view.ID)
	if err != nil {
		log.Error().Err(err).Str("view_id", view.ID).Msg("failed to fetch updated view")
		return err
	}
	tmplOut, warnings, err := svc.ViewToTemplate(ctx, updated)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Str("view_id", view.ID).Msg("failed to build view template")
		return err
	}
	return out.Write(models.NewKVTabular(tmplOut))
}
