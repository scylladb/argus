package discussions

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
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

	runID, _ := cmd.Flags().GetString("run-id")
	commentID, _ := cmd.Flags().GetString("comment-id")
	flagTestID, _ := cmd.Flags().GetString("test-id")

	svc := services.NewDiscussionService(client, c, RunFetcher)

	testID, err := svc.ResolveTestID(ctx, runID, flagTestID)
	if err != nil {
		return err
	}

	result, err := svc.DeleteComment(ctx, testID, runID, commentID)
	if err != nil {
		return err
	}

	return out.Write(models.NewTabularSlice(result))
}
