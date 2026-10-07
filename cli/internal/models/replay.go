package models

// ReplayIngestSummary mirrors argus/backend/service/replay_service.py
// `ReplaySummary.as_dict`. It is the response payload of
// `POST /api/v1/client/replay/ingest`.
type ReplayIngestSummary struct {
	Total           int                 `json:"total"`
	Processed       int                 `json:"processed"`
	Succeeded       int                 `json:"succeeded"`
	Failed          int                 `json:"failed"`
	SkippedNoReplay int                 `json:"skipped_no_replay"`
	BackfilledLogs  int                 `json:"backfilled_logs"`
	Errors          []ReplayIngestError `json:"errors"`
	Runs            []ReplayRun         `json:"runs"`
}

// ReplayRun is one run that the replay addressed. ID is the run ID after the
// server gave it any new one, and SourceID is the ID the log recorded.
// BuildID and BuildNumber name the build of a run that a replay with a build
// ID made, and are empty otherwise.
type ReplayRun struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	SourceID    string `json:"source_id"`
	BuildID     string `json:"build_id"`
	BuildNumber *int   `json:"build_number"`
}

// ReplayIngestError describes one record that the server could not replay.
type ReplayIngestError struct {
	TS       int64  `json:"ts"`
	Endpoint string `json:"endpoint"`
	Error    string `json:"error"`
}
