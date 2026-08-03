package view

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// registerWidgets adds the "widgets" sub-command to parent.
func registerWidgets(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "widgets",
		Short: "List the widget types a view can contain",
		Long: `List the widget types that can be added to a view, with their friendly name
and default settings.

The listed type identifiers are the values accepted by 'create --widget' and
'update --widget'; a widget added by type is seeded with the default settings
shown here. Use them as a reference when hand-writing a --file template too.`,
		RunE: runWidgets,
	}

	parent.AddCommand(cmd)
}

// runWidgets is the RunE handler for "view widgets".
func runWidgets(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	out := cmdctx.OutputterFrom(cmd.Context())
	return out.Write(models.AllWidgetTypeInfos())
}
