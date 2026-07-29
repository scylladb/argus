package cmd

import (
	"github.com/scylladb/argus/cli/cmd/view"
	"github.com/spf13/cobra"
)

// viewCmd is the parent command for user-view management.
var viewCmd = &cobra.Command{
	Use:   "view",
	Short: "Manage Argus user views",
	Long: `Create, inspect, and manage Argus user views.

Views are referenced by their UUID or their name (slug). View items and widget
filters are referenced by release-qualified build_system_id (a single segment is
a release, "release/group" a group, and "release/group/test" a test) and
resolved to UUIDs automatically.`,
}

func init() {
	view.Register(viewCmd)
	rootCmd.AddCommand(viewCmd)
}
