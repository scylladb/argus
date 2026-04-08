package discussions

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerDelete adds the "delete" sub-command to parent.
func registerDelete(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "delete",
		Short: "Delete a comment from a test run",
		Long: `Delete a comment you previously posted on a test run.

If --test-id is omitted it will be resolved automatically from the run.
Only the comment author can delete their comment.`,
		RunE: runDeleteComment,
	}

	cmd.Flags().String("run-id", "", "Run UUID (required)")
	cmd.Flags().String("comment-id", "", "Comment UUID (required)")
	cmd.Flags().String("test-id", "", "Test UUID (optional, resolved from the run if omitted)")
	_ = cmd.MarkFlagRequired("run-id")
	_ = cmd.MarkFlagRequired("comment-id")

	parent.AddCommand(cmd)
}

// runDeleteComment is the standalone RunE handler for "comment delete".
func runDeleteComment(cmd *cobra.Command, _ []string) error {
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "comment-delete")

	runID, _ := cmd.Flags().GetString("run-id")
	commentID, _ := cmd.Flags().GetString("comment-id")
	flagTestID, _ := cmd.Flags().GetString("test-id")

	log.Debug().Str("run_id", runID).Str("comment_id", commentID).Str("test_id", flagTestID).Msg("deleting comment")

	svc := services.NewDiscussionService(client, c, RunFetcher)

	testID, err := svc.ResolveTestID(ctx, runID, flagTestID)
	if err != nil {
		log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve test ID")
		return err
	}
	log.Debug().Str("run_id", runID).Str("test_id", testID).Msg("test ID resolved")

	result, err := svc.DeleteComment(ctx, testID, runID, commentID)
	if err != nil {
		log.Error().Err(err).Str("run_id", runID).Str("comment_id", commentID).Str("test_id", testID).Msg("failed to delete comment")
		return err
	}

	log.Info().Str("run_id", runID).Str("comment_id", commentID).Str("test_id", testID).Msg("comment deleted successfully")
	return out.Write(models.NewTabularSlice(result))
}
