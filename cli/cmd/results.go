package cmd

import (
	"errors"
	"fmt"
	"net/url"
	"strings"

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

		release, err := releasePathSegment(args[0])
		if err != nil {
			return err
		}
		showHidden, err := cmd.Flags().GetBool("show-hidden")
		if err != nil {
			return err
		}
		route := fmt.Sprintf(api.ReleaseResultTables, release)
		if showHidden {
			route += "?includeHidden=true"
		}
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
--since defaults to 30 days before --until, or before now.
Each test returns at most its 100 newest runs in the window, and runs_truncated
is true when it has more.
--sut-since and --sut-until filter on sut_timestamp, the date of the SUT build.
Time values are ISO-8601, for example 2026-10-01 or 2026-10-01T12:00:00Z.

<release> is the release name or its UUID.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "results-query")

		route, err := releaseResultsRouteFromFlags(cmd, args[0])
		if err != nil {
			return err
		}

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

// releaseResultsQuery holds the query parameters of the release results route.
type releaseResultsQuery struct {
	Table      string
	Statuses   []string
	Window     map[string]string // time-window query parameters by name
	ShowHidden bool
}

// releasePathSegment escapes release for one path segment. A dot segment
// would change the route after URL normalization, so it is an error.
func releasePathSegment(release string) (string, error) {
	if strings.Trim(release, ".") == "" {
		return "", fmt.Errorf("invalid release %q: give a release name or UUID", release)
	}
	return url.PathEscape(release), nil
}

// releaseResultsRouteFromFlags reads the query flags of cmd and builds the
// release results route for release.
func releaseResultsRouteFromFlags(cmd *cobra.Command, release string) (string, error) {
	var (
		query releaseResultsQuery
		errs  []error
		err   error
	)
	query.Table, err = cmd.Flags().GetString("table")
	errs = append(errs, err)
	query.Statuses, err = cmd.Flags().GetStringSlice("status")
	errs = append(errs, err)
	query.ShowHidden, err = cmd.Flags().GetBool("show-hidden")
	errs = append(errs, err)
	query.Window = map[string]string{}
	for flag, param := range releaseResultsWindowParams {
		value, err := cmd.Flags().GetString(flag)
		errs = append(errs, err)
		if value != "" {
			query.Window[param] = value
		}
	}
	if err := errors.Join(errs...); err != nil {
		return "", err
	}
	if strings.TrimSpace(query.Table) == "" {
		return "", errors.New("--table must not be empty")
	}
	return releaseResultsRoute(release, query)
}

// releaseResultsRoute builds the release results route.
func releaseResultsRoute(release string, query releaseResultsQuery) (string, error) {
	segment, err := releasePathSegment(release)
	if err != nil {
		return "", err
	}
	params := url.Values{}
	params.Set("table", query.Table)
	for _, s := range query.Statuses {
		params.Add("status[]", s)
	}
	for param, value := range query.Window {
		params.Set(param, value)
	}
	if query.ShowHidden {
		params.Set("includeHidden", "true")
	}
	return fmt.Sprintf(api.ReleaseResults, segment) + "?" + params.Encode(), nil
}

func init() {
	genericResultsQueryCmd.Flags().String("table", "", "Substring of the table name (required)")
	if err := genericResultsQueryCmd.MarkFlagRequired("table"); err != nil {
		panic(err)
	}
	genericResultsQueryCmd.Flags().StringSlice("status", nil, "Keep only cells with this status (repeatable): PASS, WARNING, ERROR, UNSET")
	genericResultsQueryCmd.Flags().String("since", "", "Only results received at or after this time (default: 30 days before --until, or before now)")
	genericResultsQueryCmd.Flags().String("until", "", "Only results received at or before this time")
	genericResultsQueryCmd.Flags().String("sut-since", "", "Only results with sut_timestamp at or after this time")
	genericResultsQueryCmd.Flags().String("sut-until", "", "Only results with sut_timestamp at or before this time")

	for _, cmd := range []*cobra.Command{genericResultsTablesCmd, genericResultsQueryCmd} {
		cmd.Flags().Bool("show-hidden", false, "Include the columns that the submitter marked as hidden")
	}

	genericResultsCmd.AddCommand(genericResultsTablesCmd, genericResultsQueryCmd)
	rootCmd.AddCommand(genericResultsCmd)
}
