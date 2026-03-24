package cmd

import (
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/spf13/cobra"
)

var noCache bool

// rootPreRunE is captured in init() before any child overrides it, so we can
// call it without triggering infinite Cobra PersistentPreRunE resolution.
var rootPreRunE func(cmd *cobra.Command, args []string) error

var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Inspect Argus test runs",
	Long:  "Commands for fetching run details, events, nemeses, logs, resources, and test results from Argus.",
}

func init() {
	// Capture root's hook before we override the chain.
	rootPreRunE = rootCmd.PersistentPreRunE

	runCmd.PersistentPreRunE = func(cmd *cobra.Command, args []string) error {
		if rootPreRunE != nil {
			if err := rootPreRunE(cmd, args); err != nil {
				return err
			}
		}

		c := cache.New()
		if noCache {
			c.Disable()
		}
		cmd.SetContext(contextWithCache(cmd.Context(), c))
		return nil
	}

	runCmd.PersistentFlags().BoolVar(&noCache, "no-cache", false, "bypass disk cache for API responses")

	rootCmd.AddCommand(runCmd)
	runCmd.AddCommand(
		runDetailsCmd,
		runEventsCmd,
		runNemesesCmd,
		runLogsCmd,
		runResourcesCmd,
		runTestsCmd,
	)
}
