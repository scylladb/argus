package cache

import (
	"path"
	"time"
)

// TTL constants per resource type, reflecting how quickly the underlying
// data is expected to change.
const (
	// TTLRun is the TTL for individual test run objects.
	// Runs are updated while executing, so keep it short.
	TTLRun = 5 * time.Minute

	// TTLRunType is the TTL for run-type lookups.
	// A run's type is immutable once assigned.
	TTLRunType = 24 * time.Hour

	// TTLActivity is the TTL for run activity/event logs.
	// Events are appended frequently during execution.
	TTLActivity = time.Minute

	// TTLResults is the TTL for performance/result tables.
	TTLResults = 5 * time.Minute

	// TTLComments is the TTL for comment lists.
	TTLComments = 5 * time.Minute

	// TTLPytestResults is the TTL for pytest result lists.
	TTLPytestResults = 5 * time.Minute

	// TTLVersion is the TTL for the API version response.
	// The version only changes on a new server deployment.
	TTLVersion = time.Hour

	// TTLSCTEvents is the TTL for SCT event pages fetched from the server.
	// Events are append-only once a run finishes, so a longer TTL is fine.
	// During a live run we keep it short so new events appear quickly.
	TTLSCTEvents = 5 * time.Minute
)

// RunKey returns the cache key for a specific test run.
//
// On disk: cache/runs/{runType}/{runID}/
func RunKey(runType, runID string) string {
	return path.Join("runs", runType, runID)
}

// RunTypeKey returns the cache key for a run-type lookup.
//
// On disk: cache/run-types/{runID}/
func RunTypeKey(runID string) string {
	return path.Join("run-types", runID)
}

// ActivityKey returns the cache key for a run's activity log.
//
// On disk: cache/activity/{runID}/
func ActivityKey(runID string) string {
	return path.Join("activity", runID)
}

// ResultsKey returns the cache key for a run's performance result tables.
//
// On disk: cache/results/{testID}/{runID}/
func ResultsKey(testID, runID string) string {
	return path.Join("results", testID, runID)
}

// RunCommentsKey returns the cache key for the comments on a run.
//
// On disk: cache/comments/run/{runID}/
func RunCommentsKey(runID string) string {
	return path.Join("comments", "run", runID)
}

// CommentKey returns the cache key for a single comment.
//
// On disk: cache/comments/{commentID}/
func CommentKey(commentID string) string {
	return path.Join("comments", commentID)
}

// PytestResultsKey returns the cache key for a run's pytest results.
//
// On disk: cache/pytest-results/{runID}/
func PytestResultsKey(runID string) string {
	return path.Join("pytest-results", runID)
}

// VersionKey returns the cache key for the API version endpoint.
//
// On disk: cache/version/
func VersionKey() string {
	return "version"
}

// fullCursor is the sentinel value stored in a cache key component to indicate
// that the entry covers the full (unfiltered) dataset for a run.
const fullCursor = "full"

// SCTEventsKey returns the cache key for a page of SCT events for a run.
// The key encodes the severity filter and the before/after timestamp cursors so
// that each distinct query is cached independently.
//
// On disk: cache/sct-events/{runID}/{severity}/{before}/{after}/
//
// Pass an empty string for severity to represent "all severities".
// Pass an empty string for before/after to represent "no bound on that side".
// When both before and after are empty the key represents the full dataset
// (all events, no time window); use [SCTEventsFullKey] as a shorthand.
func SCTEventsKey(runID, severity, before, after string) string {
	if severity == "" {
		severity = "all"
	}
	if before == "" {
		before = "none"
	}
	if after == "" {
		after = "none"
	}
	return path.Join("sct-events", runID, severity, before, after)
}

// SCTEventsFullKey returns the cache key that represents the complete,
// unfiltered set of SCT events for a run at the given severity level.
// This is the key written when no --before/--after flags are supplied, and
// read first when a filtered request arrives so that local filtering can be
// attempted before hitting the network.
//
// On disk: cache/sct-events/{runID}/{severity}/full/full/
func SCTEventsFullKey(runID, severity string) string {
	if severity == "" {
		severity = "all"
	}
	return path.Join("sct-events", runID, severity, fullCursor, fullCursor)
}

// NemesesKey returns the cache key for a run's nemesis records fetched from
// the dedicated nemesis endpoint (unfiltered / full dataset).
//
// On disk: cache/nemeses/{runID}/full/
func NemesesKey(runID string) string {
	return path.Join("nemeses", runID, fullCursor)
}

// NemesesFilteredKey returns the cache key for a filtered page of nemesis
// records.  The key encodes both timestamp bounds so that each distinct query
// is stored separately.
//
// On disk: cache/nemeses/{runID}/{before}/{after}/
func NemesesFilteredKey(runID, before, after string) string {
	if before == "" {
		before = "none"
	}
	if after == "" {
		after = "none"
	}
	return path.Join("nemeses", runID, before, after)
}
