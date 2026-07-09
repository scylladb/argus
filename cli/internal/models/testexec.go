package models

import (
	"encoding/json"
	"strconv"
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
// user automatically, so it must not be included here. IncludeBuildNumber opts
// in to receiving the guessed next build number in the response (an extra
// Jenkins lookup on the backend), used to derive an Argus link without waiting.
type JenkinsBuildRequest struct {
	BuildID            string         `json:"buildId"`
	Parameters         map[string]any `json:"parameters"`
	IncludeBuildNumber bool           `json:"includeBuildNumber,omitempty"`
}

// JenkinsBuildResponse is the response payload for POST /api/v1/jenkins/build.
// NextBuildNumber is the backend's best-effort guess of the build number the
// triggered build will receive; it is present only when the request set
// IncludeBuildNumber and the backend could resolve it.
type JenkinsBuildResponse struct {
	QueueItem       int `json:"queueItem"`
	NextBuildNumber int `json:"nextBuildNumber,omitempty"`
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

// ---------------------------------------------------------------------------
// Fan-out (label-based) execution results
// ---------------------------------------------------------------------------

// TriggeredBuild is one row of a fan-out execution result: the test reference
// and its build_system_id, the Jenkins queue item the build was scheduled as,
// its resolved URL (populated only when --wait is used and the build started),
// the Argus run URL (also populated on --wait once the build number is known),
// and a human-readable status.
type TriggeredBuild struct {
	Test          string `json:"test"`
	BuildSystemID string `json:"build_system_id"`
	QueueItem     int    `json:"queue_item,omitempty"`
	URL           string `json:"url,omitempty"`
	ArgusURL      string `json:"argus_url,omitempty"`
	Status        string `json:"status"`
}

// TriggeredBuilds is a fan-out execution result set. It implements
// output.Tabular for text rendering while JSON output marshals the slice
// directly.
type TriggeredBuilds []TriggeredBuild

// Headers implements output.Tabular.
func (TriggeredBuilds) Headers() []string {
	return []string{"Test", "Build System ID", "Queue Item", "URL", "Argus URL", "Status"}
}

// Rows implements output.Tabular.
func (b TriggeredBuilds) Rows() [][]string {
	rows := make([][]string, 0, len(b))
	for _, r := range b {
		queue := ""
		if r.QueueItem != 0 {
			queue = strconv.Itoa(r.QueueItem)
		}
		rows = append(rows, []string{r.Test, r.BuildSystemID, queue, r.URL, r.ArgusURL, r.Status})
	}
	return rows
}

// StartedBuild is the result of a single 'test execute --wait': the triggered
// job, its Jenkins build URL/number once scheduled, and the stable Argus run
// URL derived from the build_system_id and build number.
type StartedBuild struct {
	BuildID     string `json:"build_id"`
	JenkinsURL  string `json:"jenkins_url,omitempty"`
	BuildNumber int    `json:"build_number,omitempty"`
	ArgusURL    string `json:"argus_url,omitempty"`
}

// ExecutedBuild is the result of a single 'test execute' without --wait: the
// triggered job, its Jenkins queue item, and — when the backend could guess the
// next build number — the guessed build number and the stable Argus run URL
// derived from it. The number is a best-effort guess made at trigger time, so
// BuildNumber/ArgusURL are omitted when it isn't known.
type ExecutedBuild struct {
	BuildID     string `json:"build_id"`
	QueueItem   int    `json:"queue_item"`
	BuildNumber int    `json:"build_number,omitempty"`
	ArgusURL    string `json:"argus_url,omitempty"`
}

// ---------------------------------------------------------------------------
// Queue status snapshot (check-queue)
// ---------------------------------------------------------------------------

// QueueStatus is one row of a `test check-queue` result: the queried Jenkins
// queue item and its current state. A scheduled item carries URL/Number; an
// item still waiting carries Why. Status is a human-readable summary
// ("started", "pending", or "error: ...").
type QueueStatus struct {
	QueueItem int    `json:"queue_item"`
	Status    string `json:"status"`
	URL       string `json:"url,omitempty"`
	Number    int    `json:"number,omitempty"`
	Why       string `json:"why,omitempty"`
}

// QueueStatuses is a check-queue result set. It implements output.Tabular for
// text rendering while JSON output marshals the slice directly.
type QueueStatuses []QueueStatus

// Headers implements output.Tabular.
func (QueueStatuses) Headers() []string {
	return []string{"Queue Item", "Status", "URL", "Number", "Why"}
}

// Rows implements output.Tabular.
func (s QueueStatuses) Rows() [][]string {
	rows := make([][]string, 0, len(s))
	for _, r := range s {
		number := ""
		if r.Number != 0 {
			number = strconv.Itoa(r.Number)
		}
		rows = append(rows, []string{strconv.Itoa(r.QueueItem), r.Status, r.URL, number, r.Why})
	}
	return rows
}
