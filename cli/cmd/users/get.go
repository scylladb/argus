package users

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerGet adds the "get" sub-command to parent.
func registerGet(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "get",
		Short: "Show a single user",
		Long: `Show a single user addressed by exactly one of --username, --uuid
or --email, e.g.:
  argus users get --username alice
  argus users get --uuid 7f3c1e90-...
  argus users get --email alice@scylladb.com`,
		RunE: runGet,
	}

	cmd.Flags().String("username", "", "Look up the user by username")
	cmd.Flags().String("uuid", "", "Look up the user by UUID")
	cmd.Flags().String("email", "", "Look up the user by email")
	cmd.MarkFlagsMutuallyExclusive("username", "uuid", "email")
	cmd.MarkFlagsOneRequired("username", "uuid", "email")

	parent.AddCommand(cmd)
}

// runGet is the RunE handler for "users get".
func runGet(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "users-get")

	var field, value string
	for _, f := range []string{"username", "uuid", "email"} {
		if v, _ := cmd.Flags().GetString(f); v != "" {
			field, value = f, v
			break
		}
	}
	log.Debug().Str("field", field).Str("value", value).Msg("fetching user")

	svc := services.NewUserService(client, c)

	user, err := svc.GetUser(ctx, field, value)
	if err != nil {
		log.Error().Err(err).Str("field", field).Str("value", value).Msg("failed to fetch user")
		return err
	}

	log.Info().Str("field", field).Str("value", value).Msg("user fetched successfully")
	return out.Write(models.NewKVTabular(models.NewUserListEntry(user)))
}
