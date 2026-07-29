package view

import (
	"bufio"
	"fmt"
	"os"
	"strings"

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
		Short: "Delete a user view",
		Long: `Delete a user view addressed by its UUID or name (slug).

A confirmation prompt is shown unless --yes is given.

  argus view delete --view my-dashboard --yes
  argus view delete --view 7f3c1e90-...`,
		RunE: runDelete,
	}

	cmd.Flags().StringP("view", "i", "", "View UUID or name (required)")
	cmd.Flags().Bool("yes", false, "Skip the confirmation prompt")
	_ = cmd.MarkFlagRequired("view")

	parent.AddCommand(cmd)
}

// runDelete is the RunE handler for "view delete".
func runDelete(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "view-delete")

	viewRef, _ := cmd.Flags().GetString("view")
	yes, _ := cmd.Flags().GetBool("yes")

	svc := services.NewViewService(client, c)

	// Fetch the view for its canonical UUID and to show what is about to be
	// deleted.
	view, err := svc.GetView(ctx, viewRef)
	if err != nil {
		log.Error().Err(err).Str("view", viewRef).Msg("failed to fetch view")
		return err
	}
	summaries, err := svc.BuildSummaries(ctx, []models.View{view})
	if err != nil {
		log.Error().Err(err).Str("view", viewRef).Msg("failed to summarize view")
		return err
	}
	if err := out.Write(summaries[0]); err != nil {
		return err
	}

	if !yes {
		ok, err := confirm(cmd, fmt.Sprintf("Delete view %q?", view.Name))
		if err != nil {
			return err
		}
		if !ok {
			log.Info().Str("view_id", view.ID).Msg("deletion aborted by user")
			return out.Write(map[string]string{"status": "aborted", "view_id": view.ID})
		}
	}

	if err := svc.DeleteView(ctx, view.ID); err != nil {
		log.Error().Err(err).Str("view_id", view.ID).Msg("failed to delete view")
		return err
	}

	log.Info().Str("view_id", view.ID).Msg("view deleted successfully")
	return out.Write(map[string]string{"status": "deleted", "view_id": view.ID})
}

// confirm prints prompt to stderr and reads a y/N answer from stdin.
func confirm(cmd *cobra.Command, prompt string) (bool, error) {
	fmt.Fprintf(os.Stderr, "%s [y/N]: ", prompt)
	scanner := bufio.NewScanner(os.Stdin)
	if !scanner.Scan() {
		if err := scanner.Err(); err != nil {
			return false, fmt.Errorf("reading confirmation: %w", err)
		}
		return false, nil
	}
	answer := strings.ToLower(strings.TrimSpace(scanner.Text()))
	return answer == "y" || answer == "yes", nil
}
