package users

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerList adds the "list" sub-command to parent.
func registerList(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List all users",
		Long: `List all Argus users, showing username, email and UUID:
  argus users list`,
		RunE: runList,
	}
	parent.AddCommand(cmd)
}

// runList is the RunE handler for "users list".
func runList(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "users-list")

	svc := services.NewUserService(client, c)

	usrs, err := svc.ListUsers(ctx)
	if err != nil {
		log.Error().Err(err).Msg("failed to list users")
		return err
	}

	entries := make([]models.UserListEntry, len(usrs))
	for i, u := range usrs {
		entries[i] = models.NewUserListEntry(u)
	}

	log.Info().Int("count", len(entries)).Msg("users listed successfully")
	return out.Write(models.NewTabularSlice(entries))
}
