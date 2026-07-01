package cmd

import (
	"fmt"
	"net/url"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// ---------------------------------------------------------------------------
// Parent command: results
// ---------------------------------------------------------------------------

// crossResultsCmd is the top-level "argus results" command. Named distinctly
// from the existing (unrelated) resultsCmd in testrun.go, which implements
// "argus run results" (per-run result tables for a single test_id/run_id).
var crossResultsCmd = &cobra.Command{
	Use:   "results",
	Short: "Cross-test queries over generic result tables",
	Long: `Query Argus generic result tables across every test, without knowing
any test_id up front.`,
}

// ---------------------------------------------------------------------------
// Subcommand: results catalog
// ---------------------------------------------------------------------------

var resultsCatalogCmd = &cobra.Command{
	Use:   "catalog",
	Short: "List every distinct generic result table name system-wide",
	Long: `Lists every distinct generic result table name across all tests,
along with how many tests report a table with that name and the (merged)
column metadata for it.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "results-catalog")

		route := api.ResultsCatalog
		log.Debug().Str("route", route).Msg("fetching results catalog")

		cacheKey := cache.ResultsCatalogKey()
		if cached, _, err := cache.Get[models.ResultCatalogResponse](c, cacheKey); isCacheable(err) {
			log.Debug().Msg("results catalog served from cache")
			return out.Write(cached)
		}

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		result, err := api.DoJSON[models.ResultCatalogResponse](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to fetch results catalog")
			return err
		}

		if cacheErr := cache.Set(c, cacheKey, result, route, cache.TTLResultsCatalog); cacheErr != nil {
			log.Warn().Err(cacheErr).Msg("failed to cache results catalog")
		}

		log.Info().Int("tables", len(result)).Msg("results catalog fetched successfully")
		return out.Write(result)
	},
}

// ---------------------------------------------------------------------------
// Subcommand: results query
// ---------------------------------------------------------------------------

var resultsQueryCmd = &cobra.Command{
	Use:   "query",
	Short: "Query flattened result cells across every test",
	Long: `Fetch a flattened cell dump (one row per cell: test_id, table, run_id,
column, row, value, status, sut_timestamp) from generic result tables whose
name matches a substring, optionally filtered by status and a sut_timestamp
range, across every test.

All flags are optional. Without any flags the endpoint returns up to 500
cells across every generic result table.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "results-query")

		// Read flags.
		name, _ := cmd.Flags().GetString("name")
		limit, _ := cmd.Flags().GetInt("limit")
		before, _ := cmd.Flags().GetInt64("before")
		after, _ := cmd.Flags().GetInt64("after")
		statuses, _ := cmd.Flags().GetStringSlice("status")

		// Build query string.
		params := url.Values{}
		if name != "" {
			params.Set("name", name)
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

		qs := params.Encode()
		route := api.ResultsSearch
		if qs != "" {
			route += "?" + qs
		}

		log.Debug().Str("route", route).Msg("querying cross-test results")

		cacheKey := cache.ResultsSearchKey(qs)
		if cached, _, err := cache.Get[models.ResultSearchResponse](c, cacheKey); isCacheable(err) {
			log.Debug().Msg("results query served from cache")
			return out.Write(cached)
		}

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		result, err := api.DoJSON[models.ResultSearchResponse](client, req)
		if err != nil {
			log.Error().Err(err).Msg("failed to query cross-test results")
			return err
		}

		if cacheErr := cache.Set(c, cacheKey, result, route, cache.TTLResultsSearch); cacheErr != nil {
			log.Warn().Err(cacheErr).Msg("failed to cache results query")
		}

		log.Info().Int("total", result.Total).Int("cells", len(result.Cells)).Msg("results query fetched successfully")
		return out.Write(result)
	},
}

func init() {
	resultsQueryCmd.Flags().String("name", "", "Filter table names by substring")
	resultsQueryCmd.Flags().Int("limit", 500, "Maximum number of cells to return")
	resultsQueryCmd.Flags().Int64("before", 0, "Only cells with sut_timestamp before this Unix timestamp")
	resultsQueryCmd.Flags().Int64("after", 0, "Only cells with sut_timestamp after this Unix timestamp")
	resultsQueryCmd.Flags().StringSlice("status", nil, "Filter by cell status (repeatable)")

	crossResultsCmd.AddCommand(resultsCatalogCmd)
	crossResultsCmd.AddCommand(resultsQueryCmd)
	rootCmd.AddCommand(crossResultsCmd)
}
