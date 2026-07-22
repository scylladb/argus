package cmd

import (
	"github.com/scylladb/argus/cli/cmd/users"
	"github.com/spf13/cobra"
)

// usersCmd is the parent command for user lookups.
var usersCmd = &cobra.Command{
	Use:   "users",
	Short: "Look up Argus users",
	Long: `List Argus users or fetch a single user by username, UUID or email.

  argus users list
  argus users get --username alice`,
}

func init() {
	users.Register(usersCmd)
	rootCmd.AddCommand(usersCmd)
}
