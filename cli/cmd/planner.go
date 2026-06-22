package cmd

import (
	"github.com/scylladb/argus/cli/cmd/planner"
	"github.com/spf13/cobra"
)

// plannerCmd is the parent command for release-plan management.
var plannerCmd = &cobra.Command{
	Use:   "planner",
	Short: "Manage Argus release plans",
	Long: `Create, inspect, and manage Argus release plans.

Plans are referenced by their UUID or their human-friendly "releaseName#planNumber"
key; releases, users, tests, and groups are referenced by name (or, for tests, by
build_system_id) and resolved to UUIDs automatically.`,
}

func init() {
	planner.Register(plannerCmd)
	rootCmd.AddCommand(plannerCmd)
}
