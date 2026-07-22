package users

import "github.com/spf13/cobra"

// Register wires the users sub-commands onto parent.
func Register(parent *cobra.Command) {
	registerList(parent)
	registerGet(parent)
}
