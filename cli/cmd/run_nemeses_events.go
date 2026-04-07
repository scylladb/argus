package cmd

import (
	"context"
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
// Local filter helpers
// ---------------------------------------------------------------------------

// filterNemeses returns the subset of records whose StartTime falls within
// [afterTS, beforeTS].  A zero value for either bound means "no bound".
func filterNemeses(all []models.NemesisRecord, beforeTS, afterTS int64) []models.NemesisRecord {
	if beforeTS == 0 && afterTS == 0 {
		return all
	}
	out := make([]models.NemesisRecord, 0, len(all))
	for _, n := range all {
		if beforeTS != 0 && n.StartTime > beforeTS {
			continue
		}
		if afterTS != 0 && n.StartTime < afterTS {
			continue
		}
		out = append(out, n)
	}
	return out
}

// filterEvents returns the subset of events whose Ts timestamp falls within
// [afterTS, beforeTS].  A zero value for either bound means "no bound".
// Events whose timestamp cannot be parsed are kept (fail-open).
func filterEvents(all []models.SCTEvent, beforeTS, afterTS int64) []models.SCTEvent {
	if beforeTS == 0 && afterTS == 0 {
		return all
	}
	out := make([]models.SCTEvent, 0, len(all))
	for _, e := range all {
		ts, err := parseEventTimestamp(e.Ts)
		if err != nil {
			// Keep unparseable events rather than silently dropping them.
			out = append(out, e)
			continue
		}
		if beforeTS != 0 && ts > beforeTS {
			continue
		}
		if afterTS != 0 && ts < afterTS {
			continue
		}
		out = append(out, e)
	}
	return out
}

// parseEventTimestamp parses the Ts field of an SCTEvent.
// The backend stores it as an RFC3339 string; falls back to a plain Unix integer.
func parseEventTimestamp(ts string) (int64, error) {
	if t, err := time.Parse(time.RFC3339Nano, ts); err == nil {
		return t.Unix(), nil
	}
	if t, err := time.Parse(time.RFC3339, ts); err == nil {
		return t.Unix(), nil
	}
	if v, err := strconv.ParseInt(ts, 10, 64); err == nil {
		return v, nil
	}
	return 0, fmt.Errorf("cannot parse event timestamp %q", ts)
}

// tsFromFlag converts the string produced by parseTimeFlag (Unix seconds or
// empty) back to an int64 for use in local filtering.  Returns 0 when empty.
func tsFromFlag(s string) int64 {
	if s == "" {
		return 0
	}
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
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
		c := CacheFrom(ctx)

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

		isFiltered := beforeTS != "" || afterTS != ""
		beforeInt := tsFromFlag(beforeTS)
		afterInt := tsFromFlag(afterTS)

		var allEvents []models.SCTEvent
		for _, severity := range []string{"CRITICAL", "ERROR"} {
			severityEvents, fetchErr := fetchEventsForSeverity(
				ctx, client, c,
				runID, severity,
				beforeTS, afterTS, beforeInt, afterInt,
				isFiltered, limit,
			)
			if fetchErr != nil {
				return fetchErr
			}
			allEvents = append(allEvents, severityEvents...)
		}

		return out.Write(models.NewTabularSlice(allEvents))
	},
}

// fetchEventsForSeverity implements the cache-first strategy for one severity:
//
//  1. Try the full-dataset cache key (no filters).
//     - No filters requested → return the cached data directly.
//     - Filters requested    → apply them locally and return; no network call.
//  2. (Filtered only) Try the exact filtered cache key.
//     - Hit → return the cached filtered slice directly.
//  3. Fetch from the API, forwarding the filter params to the server.
//  4. Cache the result:
//     - Unfiltered fetch → store under the full-dataset key.
//     - Filtered fetch   → store under the specific filtered key.
func fetchEventsForSeverity(
	ctx context.Context,
	client *api.Client,
	c *cache.Cache,
	runID, severity string,
	beforeTS, afterTS string,
	beforeInt, afterInt int64,
	isFiltered bool,
	limit int,
) ([]models.SCTEvent, error) {
	fullKey := cache.SCTEventsFullKey(runID, severity)

	// Step 1: full-dataset cache.
	if full, _, err := cache.Get[[]models.SCTEvent](c, fullKey); isCacheable(err) {
		if !isFiltered {
			return full, nil
		}
		return filterEvents(full, beforeInt, afterInt), nil
	}

	// Step 2: exact filtered cache (only when filters are active).
	if isFiltered {
		filteredKey := cache.SCTEventsKey(runID, severity, beforeTS, afterTS)
		if filtered, _, err := cache.Get[[]models.SCTEvent](c, filteredKey); isCacheable(err) {
			return filtered, nil
		}
	}

	// Step 3: network fetch.
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
		return nil, err
	}
	events, err := api.DoJSON[[]models.SCTEvent](client, req)
	if err != nil {
		return nil, err
	}

	// Step 4: cache the result under the right key.
	if !isFiltered {
		_ = cache.Set(c, fullKey, events, route, cache.TTLSCTEvents)
	} else {
		filteredKey := cache.SCTEventsKey(runID, severity, beforeTS, afterTS)
		_ = cache.Set(c, filteredKey, events, route, cache.TTLSCTEvents)
	}

	return events, nil
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

		isFiltered := beforeTS != "" || afterTS != ""
		beforeInt := tsFromFlag(beforeTS)
		afterInt := tsFromFlag(afterTS)

		fullKey := cache.NemesesKey(runID)

		// Step 1: full-dataset cache.
		if full, _, err := cache.Get[[]models.NemesisRecord](c, fullKey); isCacheable(err) {
			if !isFiltered {
				return out.Write(models.NewTabularSlice(full))
			}
			// Full corpus cached — apply filters locally, skip the network.
			return out.Write(models.NewTabularSlice(filterNemeses(full, beforeInt, afterInt)))
		}

		// Step 2: exact filtered cache (only when filters are active).
		if isFiltered {
			filteredKey := cache.NemesesFilteredKey(runID, beforeTS, afterTS)
			if filtered, _, err := cache.Get[[]models.NemesisRecord](c, filteredKey); isCacheable(err) {
				return out.Write(models.NewTabularSlice(filtered))
			}
		}

		// Step 3: network fetch.
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

		// Step 4: cache the result under the right key.
		if !isFiltered {
			_ = cache.Set(c, fullKey, nemeses, route, cache.TTLNemeses)
		} else {
			filteredKey := cache.NemesesFilteredKey(runID, beforeTS, afterTS)
			_ = cache.Set(c, filteredKey, nemeses, route, cache.TTLNemeses)
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
