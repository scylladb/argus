package discussions

import (
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerUpdate adds the "update" sub-command to parent.
func registerUpdate(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "update",
		Short: "Update an existing comment",
		Long: `Edit a comment you previously posted on a test run.

The updated message can be provided via the --message flag or piped through stdin:
  echo "updated text" | argus comment update --run-id <uuid> --comment-id <uuid>

If --test-id is omitted it will be resolved automatically from the run.
Only the comment author can update their comment.`,
		RunE: runUpdateComment,
	}

	cmd.Flags().String("run-id", "", "Run UUID (required)")
	cmd.Flags().String("comment-id", "", "Comment UUID (required)")
	cmd.Flags().String("test-id", "", "Test UUID (optional, resolved from the run if omitted)")
	cmd.Flags().String("message", "", "Updated comment message (reads from stdin if omitted)")
	cmd.Flags().String("mention", "", "Comma-separated user IDs to mention")
	_ = cmd.MarkFlagRequired("run-id")
	_ = cmd.MarkFlagRequired("comment-id")

	parent.AddCommand(cmd)
}

// runUpdateComment is the standalone RunE handler for "comment update".
func runUpdateComment(cmd *cobra.Command, _ []string) error {
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

	message, err := readMessage(cmd)
	if err != nil {
		return err
	}

	mentions := ParseMentions(cmd)

	result, err := svc.UpdateComment(ctx, testID, runID, commentID, message, mentions)
	if err != nil {
		return err
	}

	return out.Write(models.NewTabularSlice(result))
}
