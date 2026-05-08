package cmd

import (
	"encoding/json"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"

	"fmt"
)

// ---------------------------------------------------------------------------
// Subcommand: run issue
// ---------------------------------------------------------------------------

var issueCmd = &cobra.Command{
	Use:   "issue",
	Short: "Commands for run issue operations",
	Long:  `Manage issues linked to test runs in Argus.`,
}

// ---------------------------------------------------------------------------
// Subcommand: run issue add
// ---------------------------------------------------------------------------

var issueAddCmd = &cobra.Command{
	Use:   "add",
	Short: "Submit an issue for a test run",
	Long: `Link an issue (GitHub or Jira) to a test run.

If --test-id is omitted it will be resolved automatically from the run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-issue-add")

		runID, _ := cmd.Flags().GetString("run-id")
		issueURL, _ := cmd.Flags().GetString("issue-url")
		flagTestID, _ := cmd.Flags().GetString("test-id")

		log.Debug().Str("run_id", runID).Str("issue_url", issueURL).Str("test_id", flagTestID).Msg("submitting issue")

		fetcher := newRunFetcher()
		testID, err := services.ResolveTestID(ctx, client, c, fetcher, runID, flagTestID)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve test ID")
			return err
		}
		log.Debug().Str("run_id", runID).Str("test_id", testID).Msg("test ID resolved")

		route := fmt.Sprintf(api.TestRunIssueSubmit, testID, runID)
		body := map[string]string{"issue_url": issueURL}
		req, err := client.NewRequest(ctx, "POST", route, body)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("route", route).Msg("failed to build request")
			return err
		}

		result, err := api.DoJSON[json.RawMessage](client, req)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("issue_url", issueURL).Msg("failed to submit issue")
			return err
		}

		log.Info().Str("run_id", runID).Str("test_id", testID).Str("issue_url", issueURL).Msg("issue submitted successfully")
		return out.Write(result)
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run issue list
// ---------------------------------------------------------------------------

var issueListCmd = &cobra.Command{
	Use:   "list",
	Short: "List issues linked to a test run or other entity",
	Long: `Fetch issues (GitHub and Jira) linked to an Argus entity.

Exactly one filter flag must be provided:
  --run-id, --release-id, --group-id, --test-id, --user-id, --view-id, --event-id`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "issue-list")

		filters := []struct {
			flag string
			key  string
		}{
			{"run-id", "run_id"},
			{"release-id", "release_id"},
			{"group-id", "group_id"},
			{"test-id", "test_id"},
			{"user-id", "user_id"},
			{"view-id", "view_id"},
			{"event-id", "event_id"},
		}

		var filterKey, entityID string
		for _, f := range filters {
			if v, _ := cmd.Flags().GetString(f.flag); v != "" {
				if filterKey != "" {
					return fmt.Errorf("only one filter flag may be specified")
				}
				filterKey = f.key
				entityID = v
			}
		}
		if filterKey == "" {
			return fmt.Errorf("one of --run-id, --release-id, --group-id, --test-id, --user-id, --view-id, or --event-id is required")
		}

		log.Debug().Str("entity_id", entityID).Str("filter_key", filterKey).Msg("listing issues")

		route := fmt.Sprintf("%s?filterKey=%s&id=%s", api.IssuesGet, filterKey, entityID)
		log.Debug().Str("route", route).Msg("fetching issues from API")

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		result, err := api.DoJSON[[]json.RawMessage](client, req)
		if err != nil {
			log.Error().Err(err).Str("entity_id", entityID).Msg("failed to fetch issues")
			return err
		}

		issues := models.ParseIssues(result)
		log.Info().Str("entity_id", entityID).Int("count", len(issues)).Msg("issues fetched successfully")
		return out.Write(models.NewTabularSlice(issues))
	},
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

func init() {
	issueAddCmd.Flags().String("run-id", "", "Run UUID (required)")
	issueAddCmd.Flags().String("issue-url", "", "Issue URL to link (required)")
	issueAddCmd.Flags().String("test-id", "", "Test UUID (optional, resolved from the run if omitted)")
	_ = issueAddCmd.MarkFlagRequired("run-id")
	_ = issueAddCmd.MarkFlagRequired("issue-url")

	issueListCmd.Flags().String("run-id", "", "Filter by run UUID")
	issueListCmd.Flags().String("release-id", "", "Filter by release UUID")
	issueListCmd.Flags().String("group-id", "", "Filter by group UUID")
	issueListCmd.Flags().String("test-id", "", "Filter by test UUID")
	issueListCmd.Flags().String("user-id", "", "Filter by user UUID")
	issueListCmd.Flags().String("view-id", "", "Filter by view UUID")
	issueListCmd.Flags().String("event-id", "", "Filter by event UUID")

	issueCmd.AddCommand(issueAddCmd, issueListCmd)
	rootCmd.AddCommand(issueCmd)
}
