package models

import (
	"encoding/json"
	"fmt"
	"strings"
)

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

// PytestFilterHit is a single result from the pytest filter endpoint.
// It extends PytestResult with optional user-defined fields.
type PytestFilterHit struct {
	Name             string            `json:"name"              table:"Name"`
	Status           PytestStatus      `json:"status"            table:"Status"`
	ID               string            `json:"id"                table:"ID"`
	TestType         string            `json:"test_type"         table:"Test Type"`
	RunID            string            `json:"run_id"            table:"Run ID"`
	TestID           string            `json:"test_id"           table:"Test ID"`
	Duration         float64           `json:"duration"          table:"Duration"`
	Message          string            `json:"message"           table:"Message"`
	SessionTimestamp string            `json:"session_timestamp" table:"Session Timestamp"`
	Markers          []string          `json:"markers"           table:"Markers"`
	UserFields       map[string]string `json:"user_fields"       table:"User Fields"`
}

// PytestFilterResponse is the response from the pytest filter endpoint.
// Only Total and Hits are used for tabular output; chart data is preserved
// for JSON output mode.
type PytestFilterResponse struct {
	Total    int               `json:"total"`
	Hits     []PytestFilterHit `json:"hits"`
	BarChart json.RawMessage   `json:"barChart"`
	PieChart json.RawMessage   `json:"pieChart"`
}

// Headers implements the Tabular interface for PytestFilterResponse.
func (PytestFilterResponse) Headers() []string {
	return []string{"Name", "Status", "ID", "Test Type", "Run ID", "Duration", "Message", "Session Timestamp", "Markers", "User Fields"}
}

// Rows implements the Tabular interface for PytestFilterResponse.
func (r PytestFilterResponse) Rows() [][]string {
	rows := make([][]string, 0, len(r.Hits))
	for _, h := range r.Hits {
		markers := strings.Join(h.Markers, ", ")
		var fields string
		if len(h.UserFields) > 0 {
			parts := make([]string, 0, len(h.UserFields))
			for k, v := range h.UserFields {
				parts = append(parts, k+"="+v)
			}
			fields = strings.Join(parts, ", ")
		}
		rows = append(rows, []string{
			h.Name,
			string(h.Status),
			h.ID,
			h.TestType,
			h.RunID,
			fmt.Sprintf("%.2f", h.Duration),
			h.Message,
			h.SessionTimestamp,
			markers,
			fields,
		})
	}
	return rows
}
