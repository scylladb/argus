package users

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerSearch adds the "search" sub-command to parent.
func registerSearch(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "search <term>",
		Short: "Search users by username, full name or email",
		Long: `Search users whose username, full name or email contains the given
term (case-insensitive substring), e.g.:
  argus users search alice
  argus users search @scylladb.com`,
		Args: cobra.ExactArgs(1),
		RunE: runSearch,
	}
	parent.AddCommand(cmd)
}

// runSearch is the RunE handler for "users search".
func runSearch(cmd *cobra.Command, args []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "users-search")

	term := args[0]
	log.Debug().Str("term", term).Msg("searching users")

	svc := services.NewUserService(client, c)

	usrs, err := svc.SearchUsers(ctx, term)
	if err != nil {
		log.Error().Err(err).Str("term", term).Msg("failed to search users")
		return err
	}

	entries := make([]models.UserListEntry, len(usrs))
	for i, u := range usrs {
		entries[i] = models.NewUserListEntry(u)
	}

	log.Info().Str("term", term).Int("count", len(entries)).Msg("users searched successfully")
	return out.Write(models.NewTabularSlice(entries))
}
