package models

// PytestStatus mirrors argus.common.enums.PytestStatus.
type PytestStatus string

const (
	PytestStatusError        PytestStatus = "error"
	PytestStatusPassed       PytestStatus = "passed"
	PytestStatusFailure      PytestStatus = "failure"
	PytestStatusSkipped      PytestStatus = "skipped"
	PytestStatusXFailed      PytestStatus = "xfailed"
	PytestStatusXPass        PytestStatus = "xpass"
	PytestStatusPassedError  PytestStatus = "passed & error"
	PytestStatusFailureError PytestStatus = "failure & error"
	PytestStatusSkippedError PytestStatus = "skipped & error"
	PytestStatusErrorError   PytestStatus = "error & error"
)

// PytestResult mirrors the PytestResultTable (v2) Cassandra model
// (table: pytest_v2).
//
// The id column is a DateTime in Cassandra and serialises as an ISO-8601
// string via ArgusJSONProvider.
type PytestResult struct {
	Name             string       `json:"name"`
	Status           PytestStatus `json:"status"`
	ID               string       `json:"id"` // DateTime PK, ISO-8601
	TestType         string       `json:"test_type"`
	RunID            string       `json:"run_id"`
	TestID           string       `json:"test_id"`
	ReleaseID        string       `json:"release_id"`
	Duration         float64      `json:"duration"`
	Message          string       `json:"message"`
	TestTimestamp    string       `json:"test_timestamp"`    // ISO-8601
	SessionTimestamp string       `json:"session_timestamp"` // ISO-8601
	Markers          []string     `json:"markers"`
}

// PytestSubmitData is the payload sent to the submit-pytest-result endpoint
// (POST /api/v1/client/pytest).
type PytestSubmitData struct {
	Name             string            `json:"name"`
	Timestamp        float64           `json:"timestamp"`
	SessionTimestamp float64           `json:"session_timestamp"`
	TestType         string            `json:"test_type"`
	RunID            string            `json:"run_id"`
	Status           PytestStatus      `json:"status"`
	Duration         float64           `json:"duration"`
	Markers          []string          `json:"markers"`
	UserFields       map[string]string `json:"user_fields"`
}

// PytestResultListResponse is the response payload for pytest result list
// endpoints.
type PytestResultListResponse = []PytestResult
