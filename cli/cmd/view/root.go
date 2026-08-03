// Package view provides the "view" cobra sub-commands (list, get, create,
// update, delete, widgets) for managing Argus user views. It is wired into the
// command tree by the parent cmd package via [Register].
package view

import "github.com/spf13/cobra"

// Register adds the view sub-commands (list, get, create, update, delete,
// widgets) to the given parent command (typically the "view" command owned by
// the cmd package).
func Register(parent *cobra.Command) {
	registerList(parent)
	registerGet(parent)
	registerCreate(parent)
	registerUpdate(parent)
	registerDelete(parent)
	registerWidgets(parent)
}
