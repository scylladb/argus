// Package planner provides the "planner" cobra sub-commands (list, get,
// create, delete) for managing Argus release plans. It is wired into the
// command tree by the parent cmd package via [Register].
package planner

import "github.com/spf13/cobra"

// Register adds the planner sub-commands (list, get, create, delete) to the
// given parent command (typically the "planner" command owned by the cmd
// package).
func Register(parent *cobra.Command) {
	registerList(parent)
	registerGet(parent)
	registerCreate(parent)
	registerDelete(parent)
}
