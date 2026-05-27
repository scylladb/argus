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
	Errors          []ReplayIngestError `json:"errors"`
}

// ReplayIngestError describes one record that the server could not replay.
type ReplayIngestError struct {
	TS       int64  `json:"ts"`
	Endpoint string `json:"endpoint"`
	Error    string `json:"error"`
}
