package cmd

import (
	"context"
	"fmt"
	"net/url"
	"sort"
	"strconv"
	"time"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/logging"
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
func filterNemeses(all []models.NemesisRunInfo, beforeTS, afterTS int64) []models.NemesisRunInfo {
	if beforeTS == 0 && afterTS == 0 {
		return all
	}
	out := make([]models.NemesisRunInfo, 0, len(all))
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

// deduplicateEvents aggregates duplicate events into their originals.
// Duplicate events (DuplicateID != "") are removed from the output; their
// timestamps are collected into the RepeatedAt field of the original event.
//
// When the original event is absent (e.g. filtered out by a time range), the
// earliest duplicate is promoted to stand in as the original and the remaining
// duplicates' timestamps are collected into its RepeatedAt field.
func deduplicateEvents(events []models.SCTEvent) []models.SCTEvent {
	idxByEventID := make(map[string]int, len(events))
	originals := make([]models.SCTEvent, 0, len(events))

	for _, e := range events {
		if e.DuplicateID == "" {
			idxByEventID[e.EventID] = len(originals)
			originals = append(originals, e)
		}
	}

	// Group orphaned duplicates (original not in the set) by DuplicateID.
	orphans := make(map[string][]models.SCTEvent)
	for _, e := range events {
		if e.DuplicateID == "" {
			continue
		}
		if idx, ok := idxByEventID[e.DuplicateID]; ok {
			originals[idx].RepeatedAt = append(originals[idx].RepeatedAt, e.Ts)
		} else {
			orphans[e.DuplicateID] = append(orphans[e.DuplicateID], e)
		}
	}

	// Promote the earliest orphan in each group; rest become its repeats.
	for _, group := range orphans {
		sort.Slice(group, func(i, j int) bool {
			return group[i].Ts < group[j].Ts
		})
		promoted := group[0]
		promoted.DuplicateID = ""
		for _, dup := range group[1:] {
			promoted.RepeatedAt = append(promoted.RepeatedAt, dup.Ts)
		}
		originals = append(originals, promoted)
	}

	return originals
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
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-events")

		runID, _ := cmd.Flags().GetString("run-id")
		beforeRaw, _ := cmd.Flags().GetString("before")
		afterRaw, _ := cmd.Flags().GetString("after")
		limit, _ := cmd.Flags().GetInt("limit")

		log.Debug().
			Str("run_id", runID).
			Str("before", beforeRaw).
			Str("after", afterRaw).
			Int("limit", limit).
			Msg("fetching SCT events")

		beforeTS, err := parseTimeFlag(beforeRaw)
		if err != nil {
			log.Error().Err(err).Str("value", beforeRaw).Msg("invalid --before flag")
			return fmt.Errorf("--before: %w", err)
		}
		afterTS, err := parseTimeFlag(afterRaw)
		if err != nil {
			log.Error().Err(err).Str("value", afterRaw).Msg("invalid --after flag")
			return fmt.Errorf("--after: %w", err)
		}

		isFiltered := beforeTS != "" || afterTS != ""
		beforeInt := tsFromFlag(beforeTS)
		afterInt := tsFromFlag(afterTS)

		if isFiltered {
			log.Debug().
				Int64("before_ts", beforeInt).
				Int64("after_ts", afterInt).
				Msg("time filters applied")
		}

		var allEvents []models.SCTEvent
		for _, severity := range []string{"CRITICAL", "ERROR"} {
			severityEvents, fetchErr := fetchEventsForSeverity(
				ctx, client, c, log,
				runID, severity,
				beforeTS, afterTS, beforeInt, afterInt,
				isFiltered, limit,
			)
			if fetchErr != nil {
				log.Error().Err(fetchErr).Str("run_id", runID).Str("severity", severity).Msg("failed to fetch events")
				return fetchErr
			}
			log.Debug().Str("severity", severity).Int("count", len(severityEvents)).Msg("events fetched for severity")
			allEvents = append(allEvents, severityEvents...)
		}

		allEvents = deduplicateEvents(allEvents)

		log.Info().Str("run_id", runID).Int("total_events", len(allEvents)).Msg("SCT events fetched successfully")
		return out.Write(models.SCTEventsResponse{RunID: runID, Events: allEvents})
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
	log zerolog.Logger,
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
			log.Debug().Str("run_id", runID).Str("severity", severity).Int("count", len(full)).Msg("events served from full cache")
			return full, nil
		}
		filtered := filterEvents(full, beforeInt, afterInt)
		log.Debug().Str("run_id", runID).Str("severity", severity).
			Int("total", len(full)).Int("filtered", len(filtered)).
			Msg("events filtered from full cache")
		return filtered, nil
	}

	// Step 2: exact filtered cache (only when filters are active).
	if isFiltered {
		filteredKey := cache.SCTEventsKey(runID, severity, beforeTS, afterTS)
		if filtered, _, err := cache.Get[[]models.SCTEvent](c, filteredKey); isCacheable(err) {
			log.Debug().Str("run_id", runID).Str("severity", severity).Int("count", len(filtered)).Msg("events served from filtered cache")
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

	log.Debug().Str("run_id", runID).Str("severity", severity).Str("route", route).Msg("fetching events from API")

	req, err := client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	events, err := api.DoJSON[[]models.SCTEvent](client, req)
	if err != nil {
		return nil, err
	}

	log.Debug().Str("run_id", runID).Str("severity", severity).Int("count", len(events)).Msg("events received from API")

	// Step 4: cache the result under the right key.
	if !isFiltered {
		if cacheErr := cache.Set(c, fullKey, events, route, cache.TTLSCTEvents); cacheErr != nil {
			log.Warn().Err(cacheErr).Str("run_id", runID).Str("severity", severity).Msg("failed to cache full events")
		}
	} else {
		filteredKey := cache.SCTEventsKey(runID, severity, beforeTS, afterTS)
		if cacheErr := cache.Set(c, filteredKey, events, route, cache.TTLSCTEvents); cacheErr != nil {
			log.Warn().Err(cacheErr).Str("run_id", runID).Str("severity", severity).Msg("failed to cache filtered events")
		}
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

Nemesis data is embedded in the run object and extracted locally; no
dedicated nemesis endpoint is required.

Time filtering with --before and --after accepts:
  - Unix timestamps (integer seconds, e.g. 1711234567)
  - RFC3339 / ISO-8601 datetimes (e.g. 2024-03-24T12:00:00Z)
  - Date strings (e.g. 2024-03-24, interpreted as UTC midnight)

The filter is applied to the nemesis start_time field.

Only SCT runs have nemesis records; this command returns an empty list
for other run types.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-nemeses")

		runID, _ := cmd.Flags().GetString("run-id")
		beforeRaw, _ := cmd.Flags().GetString("before")
		afterRaw, _ := cmd.Flags().GetString("after")

		log.Debug().Str("run_id", runID).Str("before", beforeRaw).Str("after", afterRaw).Msg("fetching nemeses")

		beforeTS, err := parseTimeFlag(beforeRaw)
		if err != nil {
			log.Error().Err(err).Str("value", beforeRaw).Msg("invalid --before flag")
			return fmt.Errorf("--before: %w", err)
		}
		afterTS, err := parseTimeFlag(afterRaw)
		if err != nil {
			log.Error().Err(err).Str("value", afterRaw).Msg("invalid --after flag")
			return fmt.Errorf("--after: %w", err)
		}

		isFiltered := beforeTS != "" || afterTS != ""
		beforeInt := tsFromFlag(beforeTS)
		afterInt := tsFromFlag(afterTS)

		if isFiltered {
			log.Debug().Int64("before_ts", beforeInt).Int64("after_ts", afterInt).Msg("time filters applied")
		}

		fullKey := cache.NemesesKey(runID)

		// Step 1: full-dataset cache.
		if full, _, err := cache.Get[[]models.NemesisRunInfo](c, fullKey); isCacheable(err) {
			if !isFiltered {
				log.Debug().Str("run_id", runID).Int("count", len(full)).Msg("nemeses served from full cache")
				return out.Write(models.NewNemesisResponse(runID, full))
			}
			filtered := filterNemeses(full, beforeInt, afterInt)
			log.Debug().Str("run_id", runID).Int("total", len(full)).Int("filtered", len(filtered)).Msg("nemeses filtered from full cache")
			return out.Write(models.NewNemesisResponse(runID, filtered))
		}

		// Step 2: exact filtered cache (only when filters are active).
		if isFiltered {
			filteredKey := cache.NemesesFilteredKey(runID, beforeTS, afterTS)
			if filtered, _, err := cache.Get[[]models.NemesisRunInfo](c, filteredKey); isCacheable(err) {
				log.Debug().Str("run_id", runID).Int("count", len(filtered)).Msg("nemeses served from filtered cache")
				return out.Write(models.NewNemesisResponse(runID, filtered))
			}
		}

		// Step 3: fetch the full run and extract nemesis_data.
		log.Debug().Str("run_id", runID).Msg("resolving run type for nemeses fetch")
		runType, err := ResolveRunType(ctx, client, runID)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("failed to resolve run type")
			return err
		}

		if runType != "scylla-cluster-tests" {
			// Other run types have no nemesis data.
			log.Info().Str("run_id", runID).Str("run_type", runType).Msg("run type has no nemesis data; returning empty list")
			return out.Write(models.NewNemesisResponse(runID, nil))
		}

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		log.Debug().Str("run_id", runID).Str("route", route).Msg("fetching full run to extract nemeses")
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("route", route).Msg("failed to build request")
			return err
		}
		run, err := api.DoJSON[models.SCTTestRun](client, req)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Msg("API request for nemeses failed")
			return err
		}

		nemeses := run.NemesisData
		log.Debug().Str("run_id", runID).Int("count", len(nemeses)).Msg("nemeses extracted from run")

		// Step 4: cache the full nemesis list, then apply filters locally.
		if cacheErr := cache.Set(c, fullKey, nemeses, route, cache.TTLRun); cacheErr != nil {
			log.Warn().Err(cacheErr).Str("run_id", runID).Msg("failed to cache nemeses")
		}

		if isFiltered {
			filtered := filterNemeses(nemeses, beforeInt, afterInt)
			filteredKey := cache.NemesesFilteredKey(runID, beforeTS, afterTS)
			if cacheErr := cache.Set(c, filteredKey, filtered, route, cache.TTLRun); cacheErr != nil {
				log.Warn().Err(cacheErr).Str("run_id", runID).Msg("failed to cache filtered nemeses")
			}
			log.Info().Str("run_id", runID).Int("total", len(nemeses)).Int("filtered", len(filtered)).Msg("nemeses fetched and filtered successfully")
			return out.Write(models.NewNemesisResponse(runID, filtered))
		}

		log.Info().Str("run_id", runID).Int("count", len(nemeses)).Msg("nemeses fetched successfully")
		return out.Write(models.NewNemesisResponse(runID, nemeses))
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
