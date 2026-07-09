package cmd

import (
	"github.com/scylladb/argus/cli/cmd/test"
	"github.com/spf13/cobra"
)

// testCmd is the parent command for Jenkins-backed test execution.
var testCmd = &cobra.Command{
	Use:   "test",
	Short: "Execute Jenkins tests and inspect their parameters",
	Long: `Inspect a test's Jenkins parameters and trigger builds.

Tests are addressed by their build_system_id (the Jenkins job path, e.g.
"scylla-2026.2/longevity/longevity-100gb"). Runs are attributed to the
authenticated user automatically.`,
}

func init() {
	test.Register(testCmd)
	rootCmd.AddCommand(testCmd)
}
