// Package test provides the "test" cobra sub-commands (params, execute,
// check-queue) for inspecting a Jenkins job's parameters, triggering test runs,
// and querying queue status through Argus. It is wired into the command tree by
// the parent cmd package via [Register].
package test

import "github.com/spf13/cobra"

// Register adds the test sub-commands (params, execute, check-queue) to the
// given parent command (typically the "test" command owned by the cmd package).
func Register(parent *cobra.Command) {
	registerParams(parent)
	registerExecute(parent)
	registerCheckQueue(parent)
}
