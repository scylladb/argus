// Package test provides the "test" cobra sub-commands (params, execute) for
// inspecting a Jenkins job's parameters and triggering test runs through Argus.
// It is wired into the command tree by the parent cmd package via [Register].
package test

import "github.com/spf13/cobra"

// Register adds the test sub-commands (params, execute) to the given parent
// command (typically the "test" command owned by the cmd package).
func Register(parent *cobra.Command) {
	registerParams(parent)
	registerExecute(parent)
}
