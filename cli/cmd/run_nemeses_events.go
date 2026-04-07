package cmd

import (
	"fmt"
	"net/url"
	"strconv"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// parseTimeFlag converts a user-supplied time value to a Unix timestamp
// string suitable for API query parameters.
//
// Accepted formats:
//   - Unix timestamp (integer seconds, e.g. "1711234567")
//   - RFC3339 / ISO-8601 datetime (e.g. "2024-03-24T12:00:00Z", "2024-03-24T12:00:00+02:00")
//   - Date only (e.g. "2024-03-24", interpreted as start-of-day UTC)
//
// Returns an empty string when value is empty.
func parseTimeFlag(value string) (string, error) {
	if value == "" {
		return "", nil
	}

	// Try integer Unix timestamp first.
	if ts, err := strconv.ParseInt(value, 10, 64); err == nil {
		return strconv.FormatInt(ts, 10), nil
	}

	// Try RFC3339 / ISO-8601 with timezone.
	if t, err := time.Parse(time.RFC3339, value); err == nil {
		return strconv.FormatInt(t.Unix(), 10), nil
	}

	// Try date-only format (YYYY-MM-DD), interpreted as UTC midnight.
	if t, err := time.Parse("2006-01-02", value); err == nil {
		return strconv.FormatInt(t.UTC().Unix(), 10), nil
	}

	return "", fmt.Errorf("cannot parse time %q: expected a Unix timestamp (integer), RFC3339 datetime (e.g. 2024-03-24T12:00:00Z), or date (YYYY-MM-DD)", value)
}

// ---------------------------------------------------------------------------
// Subcommand: run events
// ---------------------------------------------------------------------------

var runEventsCmd = &cobra.Command{
	Use:   "events",
	Short: "Fetch CRITICAL and ERROR events for an SCT test run",
	Long: `Fetch CRITICAL and ERROR events for a scylla-cluster-tests run directly
from the Argus events API.

Time filtering with --before and --after accepts:
  - Unix timestamps (integer seconds, e.g. 1711234567)
  - RFC3339 / ISO-8601 datetimes (e.g. 2024-03-24T12:00:00Z)
  - Date strings (e.g. 2024-03-24, interpreted as UTC midnight)

Only SCT runs have per-event records; for other plugin types use
"argus run activity" instead.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		beforeRaw, _ := cmd.Flags().GetString("before")
		afterRaw, _ := cmd.Flags().GetString("after")
		limit, _ := cmd.Flags().GetInt("limit")

		beforeTS, err := parseTimeFlag(beforeRaw)
		if err != nil {
			return fmt.Errorf("--before: %w", err)
		}
		afterTS, err := parseTimeFlag(afterRaw)
		if err != nil {
			return fmt.Errorf("--after: %w", err)
		}

		var allEvents []models.SCTEvent

		for _, severity := range []string{"CRITICAL", "ERROR"} {
			route := fmt.Sprintf(api.SCTEventsBySeverity, runID, severity)
			params := url.Values{}
			params.Set("limit", strconv.Itoa(limit))
			if beforeTS != "" {
				params.Set("before", beforeTS)
			}
			if afterTS != "" {
				params.Set("after", afterTS)
			}
			if q := params.Encode(); q != "" {
				route += "?" + q
			}

			req, err := client.NewRequest(ctx, "GET", route, nil)
			if err != nil {
				return err
			}
			events, err := api.DoJSON[[]models.SCTEvent](client, req)
			if err != nil {
				return err
			}
			allEvents = append(allEvents, events...)
		}

		return out.Write(models.NewTabularSlice(allEvents))
	},
}

// ---------------------------------------------------------------------------
// Subcommand: run nemeses
// ---------------------------------------------------------------------------

var runNemesesCmd = &cobra.Command{
	Use:   "nemeses",
	Short: "Fetch nemesis records for an SCT test run",
	Long: `Fetch nemesis injection records for a scylla-cluster-tests run.

Time filtering with --before and --after accepts:
  - Unix timestamps (integer seconds, e.g. 1711234567)
  - RFC3339 / ISO-8601 datetimes (e.g. 2024-03-24T12:00:00Z)
  - Date strings (e.g. 2024-03-24, interpreted as UTC midnight)

The filter is applied to the nemesis start_time field.

Only SCT runs have nemesis records; this command returns an empty list
for other run types.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)

		runID, _ := cmd.Flags().GetString("run-id")
		beforeRaw, _ := cmd.Flags().GetString("before")
		afterRaw, _ := cmd.Flags().GetString("after")

		beforeTS, err := parseTimeFlag(beforeRaw)
		if err != nil {
			return fmt.Errorf("--before: %w", err)
		}
		afterTS, err := parseTimeFlag(afterRaw)
		if err != nil {
			return fmt.Errorf("--after: %w", err)
		}

		// Only cache when no time filters are applied (filtered results
		// would otherwise shadow each other under the same key).
		useCache := beforeTS == "" && afterTS == ""
		cacheKey := cache.NemesesKey(runID)

		if useCache {
			if cached, _, err := cache.Get[[]models.NemesisRecord](c, cacheKey); isCacheable(err) {
				return out.Write(models.NewTabularSlice(cached))
			}
		}

		route := fmt.Sprintf(api.SCTNemesisGet, runID)
		params := url.Values{}
		if beforeTS != "" {
			params.Set("before", beforeTS)
		}
		if afterTS != "" {
			params.Set("after", afterTS)
		}
		if q := params.Encode(); q != "" {
			route += "?" + q
		}

		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		nemeses, err := api.DoJSON[[]models.NemesisRecord](client, req)
		if err != nil {
			return err
		}

		if useCache {
			_ = cache.Set(c, cacheKey, nemeses, route, cache.TTLNemeses)
		}

		return out.Write(models.NewTabularSlice(nemeses))
	},
}

func init() {
	// run events
	runEventsCmd.Flags().String("run-id", "", "Run UUID (required)")
	runEventsCmd.Flags().String("before", "", "Only events before this time (Unix timestamp, RFC3339, or YYYY-MM-DD)")
	runEventsCmd.Flags().String("after", "", "Only events after this time (Unix timestamp, RFC3339, or YYYY-MM-DD)")
	runEventsCmd.Flags().Int("limit", 100, "Maximum events per severity level to return")
	_ = runEventsCmd.MarkFlagRequired("run-id")

	// run nemeses
	runNemesesCmd.Flags().String("run-id", "", "Run UUID (required)")
	runNemesesCmd.Flags().String("before", "", "Only nemeses with start_time before this time (Unix timestamp, RFC3339, or YYYY-MM-DD)")
	runNemesesCmd.Flags().String("after", "", "Only nemeses with start_time after this time (Unix timestamp, RFC3339, or YYYY-MM-DD)")
	_ = runNemesesCmd.MarkFlagRequired("run-id")

	runCmd.AddCommand(runEventsCmd, runNemesesCmd)
}
