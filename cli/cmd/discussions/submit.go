package discussions

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerSubmit adds the "submit" sub-command to parent.
func registerSubmit(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "submit",
		Short: "Post a new comment on a test run",
		Long: `Submit a new comment to a test run's discussion.

The message can be provided via the --message flag or piped through stdin:
  echo "my comment" | argus comment submit --run-id <uuid>

If --test-id is omitted it will be resolved automatically from the run.`,
		RunE: runSubmitComment,
	}

	cmd.Flags().String("run-id", "", "Run UUID (required)")
	cmd.Flags().String("test-id", "", "Test UUID (optional, resolved from the run if omitted)")
	cmd.Flags().String("message", "", "Comment message (reads from stdin if omitted)")
	cmd.Flags().String("mention", "", "Comma-separated user IDs to mention")
	_ = cmd.MarkFlagRequired("run-id")

	parent.AddCommand(cmd)
}

// runSubmitComment is the standalone RunE handler for "comment submit".
func runSubmitComment(cmd *cobra.Command, _ []string) error {
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "comment-submit")

	runID, _ := cmd.Flags().GetString("run-id")
	flagTestID, _ := cmd.Flags().GetString("test-id")

	log.Debug().Str("run_id", runID).Str("test_id", flagTestID).Msg("submitting comment")

	svc := services.NewDiscussionService(client, c, RunFetcher)

	testID, err := svc.ResolveTestID(ctx, runID, flagTestID)
	if err != nil {
		log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve test ID")
		return err
	}
	log.Debug().Str("run_id", runID).Str("test_id", testID).Msg("test ID resolved")

	message, err := readMessage(cmd)
	if err != nil {
		log.Error().Err(err).Str("run_id", runID).Msg("failed to read comment message")
		return err
	}

	mentions := ParseMentions(cmd)
	if len(mentions) > 0 {
		log.Debug().Strs("mentions", mentions).Msg("mentions parsed")
	}

	result, err := svc.SubmitComment(ctx, testID, runID, message, mentions)
	if err != nil {
		log.Error().Err(err).Str("run_id", runID).Str("test_id", testID).Msg("failed to submit comment")
		return err
	}

	log.Info().Str("run_id", runID).Str("test_id", testID).Msg("comment submitted successfully")
	return out.Write(models.NewTabularSlice(result))
}
