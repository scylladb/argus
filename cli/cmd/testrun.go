package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// ---------------------------------------------------------------------------
// Run-type handler registry
// ---------------------------------------------------------------------------

// runTypeHandler fetches a single run via the typed DoJSON generic and returns
// the result as any (the concrete type is preserved for JSON marshalling and
// reflection-based tabular output).
type runTypeHandler func(*api.Client, *http.Request) (any, error)

// runTypeHandlers maps plugin names (as accepted by the --type flag) to typed
// fetch functions.  Adding a new plugin requires only a new map entry.
var runTypeHandlers = map[string]runTypeHandler{
	"scylla-cluster-tests": func(c *api.Client, r *http.Request) (any, error) {
		return api.DoJSON[models.SCTTestRun](c, r)
	},
	"generic": func(c *api.Client, r *http.Request) (any, error) {
		return api.DoJSON[models.GenericRun](c, r)
	},
	"driver-matrix-tests": func(c *api.Client, r *http.Request) (any, error) {
		return api.DoJSON[models.DriverTestRun](c, r)
	},
	"sirenada": func(c *api.Client, r *http.Request) (any, error) {
		return api.DoJSON[models.SirenadaRun](c, r)
	},
}

// validRunTypes returns a sorted, comma-separated list of recognised plugin
// type keys (for help text and error messages).
func validRunTypes() string {
	keys := make([]string, 0, len(runTypeHandlers))
	for k := range runTypeHandlers {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return strings.Join(keys, ", ")
}

// ---------------------------------------------------------------------------
// Parent command: run
// ---------------------------------------------------------------------------

var runCmd = &cobra.Command{
	Use:   "run",
	Short: "Commands for test run operations",
	Long:  `Query and inspect test runs tracked by Argus.`,
}

// ---------------------------------------------------------------------------
// Subcommand: run list
// ---------------------------------------------------------------------------

var listRunsCmd = &cobra.Command{
	Use:   "list",
	Short: "List test runs for a given test",
	Long: `Fetch test runs belonging to a test, with optional pagination
and an optional --full flag that returns complete run objects.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		testID, _ := cmd.Flags().GetString("test-id")
		limit, _ := cmd.Flags().GetInt("limit")
		before, _ := cmd.Flags().GetFloat64("before")
		after, _ := cmd.Flags().GetFloat64("after")
		full, _ := cmd.Flags().GetBool("full")

		route := fmt.Sprintf(api.TestRunsList, testID)

		// Build query string.
		sep := "?"
		addParam := func(k, v string) {
			route += sep + k + "=" + v
			sep = "&"
		}
		addParam("limit", fmt.Sprint(limit))
		if before > 0 {
			addParam("before", fmt.Sprintf("%f", before))
		}
		if after > 0 {
			addParam("after", fmt.Sprintf("%f", after))
		}
		if full {
			addParam("full", "1")
		}

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		if full {
			// Full mode returns plugin-specific objects whose shape varies.
			// Output as raw JSON.
			result, err := api.DoJSON[json.RawMessage](client, req)
			if err != nil {
				return err
			}
			return out.Write(result)
		}

		result, err := api.DoJSON[[]models.RunMeta](client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewTabularSlice(result))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run get-type
// ---------------------------------------------------------------------------

var getRunTypeCmd = &cobra.Command{
	Use:   "get-type",
	Short: "Get a test run type",
	Long:  `Fetch the run type if exists for a specific run ID.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		route := fmt.Sprintf(api.TestRunGetType, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.RunType](client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewTabularSlice([]models.RunType{result}))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run get
// ---------------------------------------------------------------------------

var getRunCmd = &cobra.Command{
	Use:   "get",
	Short: "Get a single test run",
	Long:  `Fetch the full details of a test run by its plugin type and run ID.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runType, _ := cmd.Flags().GetString("type")
		runID, _ := cmd.Flags().GetString("run-id")

		handler, ok := runTypeHandlers[runType]
		if !ok {
			return fmt.Errorf("unknown run type %q, valid types: %s", runType, validRunTypes())
		}

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		result, err := handler(client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run activity
// ---------------------------------------------------------------------------

var activityCmd = &cobra.Command{
	Use:   "activity",
	Short: "Get the activity log for a test run",
	Long:  `Fetch the event/activity log for a specific test run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")

		route := fmt.Sprintf(api.TestRunActivity, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		result, err := api.DoJSON[models.ActivityResponse](client, req)
		if err != nil {
			return err
		}
		// ActivityResponse has a manual Tabular implementation.
		return out.Write(result)
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run results
// ---------------------------------------------------------------------------

var resultsCmd = &cobra.Command{
	Use:   "results",
	Short: "Fetch result tables for a test run",
	Long:  `Fetch generic performance/result tables for a specific test run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		testID, _ := cmd.Flags().GetString("test-id")
		runID, _ := cmd.Flags().GetString("run-id")

		route := fmt.Sprintf(api.TestRunFetchResults, testID, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		// fetch_results uses a non-standard envelope ("tables" instead of
		// "response"), so we do the HTTP call and JSON decoding ourselves.
		resp, err := client.Do(req)
		if err != nil {
			return err
		}
		defer resp.Body.Close()

		raw, err := io.ReadAll(resp.Body)
		if err != nil {
			return fmt.Errorf("reading response body: %w", err)
		}

		var envelope models.FetchResultsEnvelope
		if err := json.Unmarshal(raw, &envelope); err != nil {
			return fmt.Errorf("decoding response: %w", err)
		}
		if envelope.Status != "ok" {
			return fmt.Errorf("server returned status %q", envelope.Status)
		}

		return out.Write(models.FetchResultsResponse{Tables: envelope.Tables})
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run comments
// ---------------------------------------------------------------------------

var runCommentsCmd = &cobra.Command{
	Use:   "comments",
	Short: "List comments for a test run",
	Long:  `Fetch all comments posted on a specific test run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")

		route := fmt.Sprintf(api.TestRunComments, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		result, err := api.DoJSON[models.CommentListResponse](client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewTabularSlice(result))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run pytest-results
// ---------------------------------------------------------------------------

var runPytestResultsCmd = &cobra.Command{
	Use:   "pytest-results",
	Short: "List pytest results for a test run",
	Long:  `Fetch all pytest results associated with a specific test run.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")

		route := fmt.Sprintf(api.TestRunPytestResults, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		result, err := api.DoJSON[models.PytestResultListResponse](client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewTabularSlice(result))
	},
}

// ---------------------------------------------------------------------------
// Parent command: comment
// ---------------------------------------------------------------------------

var commentCmd = &cobra.Command{
	Use:   "comment",
	Short: "Commands for comment operations",
	Long:  `Query comments tracked by Argus.`,
}

// ---------------------------------------------------------------------------
// Subcommand: comment get
// ---------------------------------------------------------------------------

var getCommentCmd = &cobra.Command{
	Use:   "get",
	Short: "Get a single comment",
	Long:  `Fetch the full details of a comment by its ID.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		commentID, _ := cmd.Flags().GetString("comment-id")

		route := fmt.Sprintf(api.CommentGet, commentID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		result, err := api.DoJSON[models.Comment](client, req)
		if err != nil {
			return err
		}
		return out.Write(models.NewKVTabular(result))
	},
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

func init() {
	// run list
	listRunsCmd.Flags().String("test-id", "", "Test UUID (required)")
	listRunsCmd.Flags().Int("limit", 10, "Maximum number of runs to return")
	listRunsCmd.Flags().Float64("before", 0, "Only runs submitted before this Unix timestamp")
	listRunsCmd.Flags().Float64("after", 0, "Only runs submitted after this Unix timestamp")
	listRunsCmd.Flags().Bool("full", false, "Return complete run objects instead of metadata")
	_ = listRunsCmd.MarkFlagRequired("test-id")

	// run get
	getRunCmd.Flags().String("type", "", "Plugin type (required): "+validRunTypes())
	getRunCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = getRunCmd.MarkFlagRequired("type")
	_ = getRunCmd.MarkFlagRequired("run-id")

	// run get-type
	getRunTypeCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = getRunTypeCmd.MarkFlagRequired("run-id")

	// run activity
	activityCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = activityCmd.MarkFlagRequired("run-id")

	// run results
	resultsCmd.Flags().String("test-id", "", "Test UUID (required)")
	resultsCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = resultsCmd.MarkFlagRequired("test-id")
	_ = resultsCmd.MarkFlagRequired("run-id")

	// run comments
	runCommentsCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = runCommentsCmd.MarkFlagRequired("run-id")

	// run pytest-results
	runPytestResultsCmd.Flags().String("run-id", "", "Run UUID (required)")
	_ = runPytestResultsCmd.MarkFlagRequired("run-id")

	// comment get
	getCommentCmd.Flags().String("comment-id", "", "Comment UUID (required)")
	_ = getCommentCmd.MarkFlagRequired("comment-id")

	runCmd.AddCommand(listRunsCmd, getRunCmd, getRunTypeCmd, activityCmd, resultsCmd, runCommentsCmd, runPytestResultsCmd)
	commentCmd.AddCommand(getCommentCmd)
	rootCmd.AddCommand(runCmd, commentCmd)
}
