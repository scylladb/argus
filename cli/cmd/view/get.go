package view

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
		Short: "Show a single user view",
		Long: `Show a single user view addressed by its UUID or its name (slug), e.g.:
  argus view get --view my-dashboard
  argus view get --view 7f3c1e90-...

By default the view is emitted as a reference-based template (the same schema
'create --file' / 'update --file' accept) so it can be edited and re-applied:
  argus view get --view my-dashboard > view.json

Items and widget filters are shown as release-qualified build_system_id
references (a single segment is a release, "release/group" a group, and
"release/group/test" a test). Use --raw for the unresolved JSON exactly as the
backend returns it (UUID membership).`,
		RunE: runGet,
	}

	cmd.Flags().StringP("view", "i", "", "View UUID or name (required)")
	cmd.Flags().Bool("raw", false, "Emit the raw view as returned by the API (UUIDs, unresolved)")
	_ = cmd.MarkFlagRequired("view")

	parent.AddCommand(cmd)
}

// runGet is the RunE handler for "view get".
func runGet(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "view-get")

	viewRef, _ := cmd.Flags().GetString("view")
	raw, _ := cmd.Flags().GetBool("raw")
	log.Debug().Str("view", viewRef).Bool("raw", raw).Msg("fetching view")

	svc := services.NewViewService(client, c)

	view, err := svc.GetView(ctx, viewRef)
	if err != nil {
		log.Error().Err(err).Str("view", viewRef).Msg("failed to fetch view")
		return err
	}

	if raw {
		log.Info().Str("view", viewRef).Msg("view fetched successfully (raw)")
		return out.Write(models.NewKVTabular(view))
	}

	tmpl, warnings, err := svc.ViewToTemplate(ctx, view)
	for _, w := range warnings {
		log.Warn().Msg(w)
	}
	if err != nil {
		log.Error().Err(err).Str("view", viewRef).Msg("failed to build view template")
		return err
	}
	log.Info().Str("view", viewRef).Msg("view template built successfully")
	return out.Write(models.NewKVTabular(tmpl))
}
