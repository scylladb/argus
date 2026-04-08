package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/cmd/discussions"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// ---------------------------------------------------------------------------
// Run-type handler registry
// ---------------------------------------------------------------------------

// runTypeHandler fetches a single run via the typed DoJSON generic and returns
// the result as any (the concrete type is preserved for JSON marshalling and
// reflection-based tabular output).
type runTypeHandler func(*api.Client, *http.Request) (any, error)

// RunTypeHandlers maps plugin names (as accepted by the --type flag) to typed
// fetch functions.  Adding a new plugin requires only a new map entry.
var RunTypeHandlers = map[string]runTypeHandler{
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

// runTypeCacheGetter retrieves a typed run from the cache and returns it as any.
type runTypeCacheGetter func(c *cache.Cache, key string) (any, error)

// runTypeCacheGetters mirrors runTypeHandlers for cache lookups.
// Each entry must correspond to the same key in runTypeHandlers.
var runTypeCacheGetters = map[string]runTypeCacheGetter{
	"scylla-cluster-tests": func(c *cache.Cache, key string) (any, error) {
		v, _, err := cache.Get[models.SCTTestRun](c, key)
		return v, err
	},
	"generic": func(c *cache.Cache, key string) (any, error) {
		v, _, err := cache.Get[models.GenericRun](c, key)
		return v, err
	},
	"driver-matrix-tests": func(c *cache.Cache, key string) (any, error) {
		v, _, err := cache.Get[models.DriverTestRun](c, key)
		return v, err
	},
	"sirenada": func(c *cache.Cache, key string) (any, error) {
		v, _, err := cache.Get[models.SirenadaRun](c, key)
		return v, err
	},
}

// runTypeCacheSetter stores a typed run value in the cache.
// The value parameter is the concrete type returned by the matching runTypeHandler.
type runTypeCacheSetter func(c *cache.Cache, key string, value any) error

// runTypeCacheSetters mirrors runTypeHandlers for cache writes.
var runTypeCacheSetters = map[string]runTypeCacheSetter{
	"scylla-cluster-tests": func(c *cache.Cache, key string, value any) error {
		v, ok := value.(models.SCTTestRun)
		if !ok {
			return nil
		}
		return cache.Set(c, key, v, "", cache.TTLRun)
	},
	"generic": func(c *cache.Cache, key string, value any) error {
		v, ok := value.(models.GenericRun)
		if !ok {
			return nil
		}
		return cache.Set(c, key, v, "", cache.TTLRun)
	},
	"driver-matrix-tests": func(c *cache.Cache, key string, value any) error {
		v, ok := value.(models.DriverTestRun)
		if !ok {
			return nil
		}
		return cache.Set(c, key, v, "", cache.TTLRun)
	},
	"sirenada": func(c *cache.Cache, key string, value any) error {
		v, ok := value.(models.SirenadaRun)
		if !ok {
			return nil
		}
		return cache.Set(c, key, v, "", cache.TTLRun)
	},
}

// isCacheable reports whether an error from a cache getter should be treated
// as a miss (i.e. proceed to network).  Any non-nil error other than
// ErrExpired is unexpected and is logged, but we still fall through to the
// network so the user is never left without a result.
func isCacheable(err error) bool {
	return err == nil
}

// ResolveRunType fetches the plugin/type name for a run from the get-type
// endpoint, so callers don't have to supply --type manually.
func ResolveRunType(ctx context.Context, client *api.Client, runID string) (string, error) {
	req, err := client.NewRequest(ctx, "GET", fmt.Sprintf(api.TestRunGetType, runID), nil)
	if err != nil {
		return "", err
	}
	rt, err := api.DoJSON[models.RunType](client, req)
	if err != nil {
		return "", fmt.Errorf("resolving run type for %s: %w", runID, err)
	}
	return rt.RunType, nil
}

// ValidRunTypes returns a sorted, comma-separated list of recognised plugin
// type keys (for help text and error messages).
func ValidRunTypes() string {
	keys := make([]string, 0, len(RunTypeHandlers))
	for k := range RunTypeHandlers {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return strings.Join(keys, ", ")
}

// newRunFetcher constructs the RunFetcher used by discussion commands to
// resolve test IDs.  It delegates to the cmd-level run-type handler registry
// and cache maps.
func newRunFetcher() services.RunFetcher {
	return services.NewRunFetcher(
		// resolveRunType
		func(ctx context.Context, client *api.Client, runID string) (string, error) {
			return ResolveRunType(ctx, client, runID)
		},
		// fetchRun (with cache)
		func(ctx context.Context, client *api.Client, c *cache.Cache, runType, runID string) (any, error) {
			handler, ok := RunTypeHandlers[runType]
			if !ok {
				return nil, fmt.Errorf("unknown run type %q returned by server", runType)
			}

			cacheKey := cache.RunKey(runType, runID)
			if getter, ok := runTypeCacheGetters[runType]; ok {
				if cached, err := getter(c, cacheKey); isCacheable(err) {
					return cached, nil
				}
			}

			route := fmt.Sprintf(api.TestRunGet, runType, runID)
			req, err := client.NewRequest(ctx, "GET", route, nil)
			if err != nil {
				return nil, err
			}
			result, err := handler(client, req)
			if err != nil {
				return nil, err
			}

			if setter, ok := runTypeCacheSetters[runType]; ok {
				_ = setter(c, cacheKey, result)
			}

			return result, nil
		},
	)
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
		c := CacheFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		cacheKey := cache.RunTypeKey(runID)

		if cached, _, err := cache.Get[models.RunType](c, cacheKey); isCacheable(err) {
			return out.Write(models.NewTabularSlice([]models.RunType{cached}))
		}

		route := fmt.Sprintf(api.TestRunGetType, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.RunType](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLRunType)
		return out.Write(models.NewTabularSlice([]models.RunType{result}))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run get
// ---------------------------------------------------------------------------

var getRunCmd = &cobra.Command{
	Use:   "get",
	Short: "Get a single test run",
	Long: `Fetch the full details of a test run by its run ID.

When --type is omitted the plugin type is resolved automatically via the
/run/<run_id>/type endpoint and cached for 24 h so subsequent invocations
require no network round-trip for type resolution.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)

		runType, _ := cmd.Flags().GetString("type")
		runID, _ := cmd.Flags().GetString("run-id")

		// Auto-resolve run type when --type is not provided.
		if runType == "" {
			// Check cache first (long TTL — run type is immutable).
			typeKey := cache.RunTypeKey(runID)
			if cached, _, err := cache.Get[models.RunType](c, typeKey); isCacheable(err) {
				runType = cached.RunType
			} else {
				var resolveErr error
				runType, resolveErr = ResolveRunType(ctx, client, runID)
				if resolveErr != nil {
					return resolveErr
				}
				// Cache the resolved type with the long TTL.
				_ = cache.Set(c, typeKey, models.RunType{RunType: runType}, fmt.Sprintf(api.TestRunGetType, runID), cache.TTLRunType)
			}
		}

		handler, ok := RunTypeHandlers[runType]
		if !ok {
			return fmt.Errorf("unknown run type %q, valid types: %s", runType, ValidRunTypes())
		}

		cacheKey := cache.RunKey(runType, runID)

		if getter, ok := runTypeCacheGetters[runType]; ok {
			if cached, err := getter(c, cacheKey); isCacheable(err) {
				if sct, ok := cached.(models.SCTTestRun); ok {
					return out.Write(models.RunDetails{Run: sct})
				}
				return out.Write(models.NewKVTabular(cached))
			}
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
		if setter, ok := runTypeCacheSetters[runType]; ok {
			_ = setter(c, cacheKey, result)
		}

		// For SCT runs use the structured RunDetails view (mirrors the Argus
		// Details page).  All other run types fall back to the generic KV table.
		if sct, ok := result.(models.SCTTestRun); ok {
			return out.Write(models.RunDetails{Run: sct})
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
		c := CacheFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		cacheKey := cache.ActivityKey(runID)

		if cached, _, err := cache.Get[models.ActivityResponse](c, cacheKey); isCacheable(err) {
			return out.Write(cached)
		}

		route := fmt.Sprintf(api.TestRunActivity, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.ActivityResponse](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLActivity)
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
		c := CacheFrom(ctx)

		testID, _ := cmd.Flags().GetString("test-id")
		runID, _ := cmd.Flags().GetString("run-id")
		cacheKey := cache.ResultsKey(testID, runID)

		if cached, _, err := cache.Get[models.FetchResultsResponse](c, cacheKey); isCacheable(err) {
			return out.Write(cached)
		}

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
		defer func() { _ = resp.Body.Close() }()

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

		result := models.FetchResultsResponse{Tables: envelope.Tables}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLResults)
		return out.Write(result)
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
		c := CacheFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		cacheKey := cache.RunCommentsKey(runID)

		if cached, _, err := cache.Get[models.CommentListResponse](c, cacheKey); isCacheable(err) {
			return out.Write(models.NewTabularSlice(cached))
		}

		route := fmt.Sprintf(api.TestRunComments, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.CommentListResponse](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLComments)
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
		c := CacheFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		cacheKey := cache.PytestResultsKey(runID)

		if cached, _, err := cache.Get[models.PytestResultListResponse](c, cacheKey); isCacheable(err) {
			return out.Write(models.NewTabularSlice(cached))
		}

		route := fmt.Sprintf(api.TestRunPytestResults, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.PytestResultListResponse](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLPytestResults)
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
		c := CacheFrom(ctx)

		commentID, _ := cmd.Flags().GetString("comment-id")
		cacheKey := cache.CommentKey(commentID)

		if cached, _, err := cache.Get[models.Comment](c, cacheKey); isCacheable(err) {
			return out.Write(models.NewKVTabular(cached))
		}

		route := fmt.Sprintf(api.CommentGet, commentID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := api.DoJSON[models.Comment](client, req)
		if err != nil {
			return err
		}
		_ = cache.Set(c, cacheKey, result, route, cache.TTLComments)
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
	getRunCmd.Flags().String("type", "", "Plugin type (optional, auto-resolved when omitted): "+ValidRunTypes())
	getRunCmd.Flags().String("run-id", "", "Run UUID (required)")
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

	// Wire in the discussions sub-package for comment write commands.
	discussions.RunFetcher = newRunFetcher()
	discussions.Register(commentCmd)

	runCmd.AddCommand(listRunsCmd, getRunCmd, getRunTypeCmd, activityCmd, resultsCmd, runCommentsCmd, runPytestResultsCmd)
	commentCmd.AddCommand(getCommentCmd)
	rootCmd.AddCommand(runCmd, commentCmd)
}
