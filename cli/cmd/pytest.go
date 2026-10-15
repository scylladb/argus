package cmd

import (
	"fmt"
	"net/url"
	"slices"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// ---------------------------------------------------------------------------
// Parent command: pytest
// ---------------------------------------------------------------------------

var pytestCmd = &cobra.Command{
	Use:   "pytest",
	Short: "Commands for pytest result operations",
	Long:  `Query and inspect pytest results tracked by Argus.`,
}

// ---------------------------------------------------------------------------
// Subcommand: pytest results
// ---------------------------------------------------------------------------

var pytestResultsCmd = &cobra.Command{
	Use:   "results",
	Short: "Query filtered pytest results",
	Long: `Fetch pytest results with optional filtering by test name, status,
time range, markers, user-defined fields, and free-text search.

All flags are optional. Without any flags the endpoint returns the most
recent 500 failed results across all tests: the statuses the DTest tab shows
by default. --status picks other statuses, and --status "" returns every
status.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "pytest-results")

		// Read flags.
		test, _ := cmd.Flags().GetString("test")
		limit, _ := cmd.Flags().GetInt("limit")
		before, _ := cmd.Flags().GetInt64("before")
		after, _ := cmd.Flags().GetInt64("after")
		query, _ := cmd.Flags().GetString("query")
		filters, _ := cmd.Flags().GetStringSlice("filter")
		markers, _ := cmd.Flags().GetStringSlice("marker")

		statuses, err := pytestStatusFilter(cmd)
		if err != nil {
			return err
		}

		// Build query string.
		params := url.Values{}
		if test != "" {
			params.Set("test", test)
		}
		if limit > 0 {
			params.Set("limit", fmt.Sprint(limit))
		}
		if before > 0 {
			params.Set("before", fmt.Sprint(before))
		}
		if after > 0 {
			params.Set("after", fmt.Sprint(after))
		}
		for _, s := range statuses {
			params.Add("status[]", s)
		}
		if query != "" {
			params.Set("query", query)
		}
		for _, f := range filters {
			params.Add("filters[]", f)
		}
		for _, m := range markers {
			params.Add("markers[]", m)
		}

		qs := params.Encode()
		route := api.PytestFilterResults
		if qs != "" {
			route += "?" + qs
		}

		log.Debug().Str("route", route).Msg("fetching filtered pytest results")

		// Check cache.
		cacheKey := cache.PytestFilterKey(qs)
		if cached, _, err := cache.Get[models.PytestFilterResponse](c, cacheKey); isCacheable(err) {
			log.Debug().Msg("pytest filter results served from cache")
			return out.Write(cached)
		}

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		result, err := api.DoJSON[models.PytestFilterResponse](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to fetch filtered pytest results")
			return err
		}

		if cacheErr := cache.Set(c, cacheKey, result, route, cache.TTLPytestFilter); cacheErr != nil {
			log.Warn().Err(cacheErr).Msg("failed to cache pytest filter results")
		}

		log.Info().Int("total", result.Total).Int("hits", len(result.Hits)).Msg("pytest filter results fetched successfully")
		return out.Write(result)
	},
}

// addPytestStatusFlag registers the --status filter that pytestStatusFilter
// reads.
func addPytestStatusFlag(cmd *cobra.Command) {
	cmd.Flags().StringSlice("status", nil,
		"Only results with these statuses (repeatable or comma-separated; default: "+
			strings.Join(services.DefaultPytestStatuses(), ", ")+
			"); an empty value (--status \"\") lifts the filter and returns every status: "+
			strings.Join(services.PytestStatuses, ", "))
}

// pytestStatusFilter returns the statuses --status allows: the DTest default
// when the flag is not given, and the given statuses otherwise. An empty
// result allows every status.
func pytestStatusFilter(cmd *cobra.Command) ([]string, error) {
	if !cmd.Flags().Changed("status") {
		return services.DefaultPytestStatuses(), nil
	}
	raw, _ := cmd.Flags().GetStringSlice("status")
	return services.ParsePytestStatuses(raw)
}

// filterPytestResults keeps the results whose status is in statuses. An empty
// statuses keeps every result.
func filterPytestResults(results []models.PytestResult, statuses []string) []models.PytestResult {
	if len(statuses) == 0 {
		return results
	}
	kept := make([]models.PytestResult, 0, len(results))
	for _, r := range results {
		if slices.Contains(statuses, string(r.Status)) {
			kept = append(kept, r)
		}
	}
	return kept
}

func init() {
	pytestResultsCmd.Flags().String("test", "", "Filter test names by substring")
	pytestResultsCmd.Flags().Int("limit", 500, "Maximum number of results to return")
	pytestResultsCmd.Flags().Int64("before", 0, "Only results before this Unix timestamp")
	pytestResultsCmd.Flags().Int64("after", 0, "Only results after this Unix timestamp")
	addPytestStatusFlag(pytestResultsCmd)
	pytestResultsCmd.Flags().String("query", "", "Regex search pattern across result name/message/markers")
	pytestResultsCmd.Flags().StringSlice("filter", nil, "User-field filter (repeatable, format: [!]field=value)")
	pytestResultsCmd.Flags().StringSlice("marker", nil, "Pytest marker filter (repeatable)")

	pytestCmd.AddCommand(pytestResultsCmd)
	rootCmd.AddCommand(pytestCmd)
}
