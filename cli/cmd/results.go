package cmd

import (
	"fmt"
	"net/url"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

var genericResultsCmd = &cobra.Command{
	Use:   "results",
	Short: "Read generic result tables across the tests of a release",
}

var genericResultsTablesCmd = &cobra.Command{
	Use:   "tables <release>",
	Short: "List the generic result table names of a release",
	Long: `List every generic result table name that the tests of a release submit,
with the number of tests and the columns of each table.

<release> is the release name or its UUID.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "results-tables")

		route := fmt.Sprintf(api.ReleaseResultTables, url.PathEscape(args[0]))
		req, err := APIClientFrom(ctx).NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		tables, err := api.DoJSON[models.ResultTableSummaries](APIClientFrom(ctx), req)
		if err != nil {
			log.Error().Err(err).Msg("failed to fetch release result tables")
			return err
		}
		return OutputterFrom(ctx).Write(tables)
	},
}

var genericResultsQueryCmd = &cobra.Command{
	Use:   "query <release>",
	Short: "Read the generic results of a release, grouped by table, test and run",
	Long: `Read the generic results of every test in a release for the tables whose
name contains --table (case-insensitive).

The output groups the results by table, then by test with its build ID, then by
run. --since and --until filter on the time Argus received the result.
--since defaults to 30 days ago.
--sut-since and --sut-until filter on sut_timestamp, the date of the SUT build.
Time values are ISO-8601, for example 2026-10-01 or 2026-10-01T12:00:00Z.

<release> is the release name or its UUID.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "results-query")

		table, _ := cmd.Flags().GetString("table")
		statuses, _ := cmd.Flags().GetStringSlice("status")
		window := map[string]string{}
		for flag, param := range releaseResultsWindowParams {
			if value, _ := cmd.Flags().GetString(flag); value != "" {
				window[param] = value
			}
		}
		route := releaseResultsRoute(args[0], table, statuses, window)

		log.Debug().Str("route", route).Msg("fetching release results")
		req, err := APIClientFrom(ctx).NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("route", route).Msg("failed to build request")
			return err
		}

		groups, err := api.DoJSON[models.ResultGroups](APIClientFrom(ctx), req)
		if err != nil {
			log.Error().Err(err).Msg("failed to fetch release results")
			return err
		}
		return OutputterFrom(ctx).Write(groups)
	},
}

// releaseResultsWindowParams maps each time-window flag to its query parameter.
var releaseResultsWindowParams = map[string]string{
	"since": "since", "until": "until", "sut-since": "sutSince", "sut-until": "sutUntil",
}

// releaseResultsRoute builds the release results route. window holds the
// time-window query parameters by name.
func releaseResultsRoute(release, table string, statuses []string, window map[string]string) string {
	params := url.Values{}
	params.Set("table", table)
	for _, s := range statuses {
		params.Add("status[]", s)
	}
	for param, value := range window {
		params.Set(param, value)
	}
	return fmt.Sprintf(api.ReleaseResults, url.PathEscape(release)) + "?" + params.Encode()
}

func init() {
	genericResultsQueryCmd.Flags().String("table", "", "Substring of the table name (required)")
	_ = genericResultsQueryCmd.MarkFlagRequired("table")
	genericResultsQueryCmd.Flags().StringSlice("status", nil, "Keep only cells with this status (repeatable): PASS, WARNING, ERROR, UNSET")
	genericResultsQueryCmd.Flags().String("since", "", "Only results received at or after this time (default: 30 days ago)")
	genericResultsQueryCmd.Flags().String("until", "", "Only results received at or before this time")
	genericResultsQueryCmd.Flags().String("sut-since", "", "Only results with sut_timestamp at or after this time")
	genericResultsQueryCmd.Flags().String("sut-until", "", "Only results with sut_timestamp at or before this time")

	genericResultsCmd.AddCommand(genericResultsTablesCmd, genericResultsQueryCmd)
	rootCmd.AddCommand(genericResultsCmd)
}
