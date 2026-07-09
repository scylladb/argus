package models

import (
	"encoding/json"
	"strings"
)

// ---------------------------------------------------------------------------
// Jenkins test-execution payloads
// ---------------------------------------------------------------------------

// JenkinsParameter is a single Jenkins job parameter as returned by
// POST /api/v1/jenkins/params. Value is untyped because Jenkins parameter
// values may be strings, booleans, or numbers. Choices (when present) enumerate
// the allowed values for a choice parameter.
type JenkinsParameter struct {
	Name        string   `json:"name"`
	Value       any      `json:"value"`
	Description string   `json:"description,omitempty"`
	Choices     []string `json:"choices,omitempty"`
}

// JenkinsParamsRequest is the request body for POST /api/v1/jenkins/params.
// BuildNumber is a pointer so that a nil value is encoded as JSON null, which
// the backend interprets as "seed from the last build (or job defaults)".
type JenkinsParamsRequest struct {
	BuildID     string `json:"buildId"`
	BuildNumber *int   `json:"buildNumber"`
}

// JenkinsParamsResponse is the response payload for POST /api/v1/jenkins/params.
type JenkinsParamsResponse struct {
	Parameters []JenkinsParameter `json:"parameters"`
}

// JenkinsBuildRequest is the request body for POST /api/v1/jenkins/build. The
// backend adds the reserved requested_by_user parameter from the authenticated
// user automatically, so it must not be included here.
type JenkinsBuildRequest struct {
	BuildID    string         `json:"buildId"`
	Parameters map[string]any `json:"parameters"`
}

// JenkinsBuildResponse is the response payload for POST /api/v1/jenkins/build.
type JenkinsBuildResponse struct {
	QueueItem int `json:"queueItem"`
}

// JenkinsQueueInfo is the response payload for GET /api/v1/jenkins/queue_info.
// It is a union: once the queued item has been scheduled onto an executor, URL
// (and Number) are populated; while the item is still waiting, Why /
// InQueueSince / TaskURL describe the pending state.
type JenkinsQueueInfo struct {
	URL          string `json:"url,omitempty"`
	Number       int    `json:"number,omitempty"`
	Why          string `json:"why,omitempty"`
	InQueueSince int64  `json:"inQueueSince,omitempty"`
	TaskURL      string `json:"taskUrl,omitempty"`
}

// Scheduled reports whether the queued item has been assigned a build (i.e. it
// has an executable URL) rather than still waiting in the queue.
func (q JenkinsQueueInfo) Scheduled() bool { return q.URL != "" }

// ---------------------------------------------------------------------------
// Rich (--full) parameter table
// ---------------------------------------------------------------------------

// ParamsTable adapts a Jenkins parameter list to output.Tabular for the
// `test params --full` view: a multi-column table of name / value / description
// / choices. It implements json.Marshaler so JSON output emits the underlying
// []JenkinsParameter (with the real choices array), not the flattened rows.
type ParamsTable struct{ params []JenkinsParameter }

// NewParamsTable wraps a parameter list for --full rendering.
func NewParamsTable(params []JenkinsParameter) *ParamsTable {
	return &ParamsTable{params: params}
}

// Headers implements output.Tabular.
func (*ParamsTable) Headers() []string {
	return []string{"Name", "Value", "Description", "Choices"}
}

// Rows implements output.Tabular.
func (p *ParamsTable) Rows() [][]string {
	rows := make([][]string, 0, len(p.params))
	for _, param := range p.params {
		rows = append(rows, []string{
			param.Name,
			paramValueString(param.Value),
			param.Description,
			strings.Join(param.Choices, ", "),
		})
	}
	return rows
}

// MarshalJSON implements json.Marshaler so the JSON outputter serialises the
// wrapped parameter list directly, not the ParamsTable wrapper.
func (p *ParamsTable) MarshalJSON() ([]byte, error) {
	return json.Marshal(p.params)
}

// paramValueString renders a parameter value (which may be a string, bool, or
// number) as a single table cell.
func paramValueString(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	b, err := json.Marshal(v)
	if err != nil {
		return ""
	}
	return string(b)
}
