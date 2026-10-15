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

// ReplayRun is one run that the replay addressed, under the run ID that the
// log recorded. BuildID and BuildNumber name the build of a new run in the
// local-runs path, and are empty otherwise. Failed is set when the submit_run
// of the run failed in this replay.
type ReplayRun struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	BuildID     string `json:"build_id"`
	BuildNumber *int   `json:"build_number"`
	Failed      bool   `json:"failed"`
}

// ReplayIngestError describes one record that the server could not replay.
type ReplayIngestError struct {
	TS       int64  `json:"ts"`
	Endpoint string `json:"endpoint"`
	Error    string `json:"error"`
}
