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

	// TTLNemeses is an alias kept for backwards compatibility with code that
	// references the old name.  New code should prefer TTLNemesis.
	TTLNemeses = TTLRun

	// TTLNemesis is the TTL for the nemesis summary derived from a cached run.
	// Nemesis data is part of the run object itself and shares its TTL.
	TTLNemesis = TTLRun
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

// SCTEventsKey returns the cache key for a page of SCT events for a run.
// The key encodes the severity filter and the before-timestamp cursor so that
// each distinct page is cached independently.
//
// On disk: cache/sct-events/{runID}/{severity}/{before}/
// Pass an empty string for severity to represent "all severities".
// Pass an empty string for before to represent the first/latest page.
func SCTEventsKey(runID, severity, before string) string {
	if severity == "" {
		severity = "all"
	}
	if before == "" {
		before = "latest"
	}
	return path.Join("sct-events", runID, severity, before)
}

// NemesisKey returns the cache key for the nemesis summary of a run.
// The nemesis data is derived from the run object itself.
//
// On disk: cache/nemesis/{runID}/
func NemesisKey(runID string) string {
	return path.Join("nemesis", runID)
}

// NemesesKey returns the cache key for a run's nemesis records fetched from
// the dedicated nemesis endpoint.  Kept alongside NemesisKey to support both
// the legacy endpoint-based fetch and the run-object-derived summary.
//
// On disk: cache/nemeses/{runID}/
func NemesesKey(runID string) string {
	return path.Join("nemeses", runID)
}
