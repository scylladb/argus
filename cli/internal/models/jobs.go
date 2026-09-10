package models

import "strconv"

// UserJobRun is one row of GET /api/v1/user/jobs (and the team variant): a
// run assigned to the user within the server's job validity window. Assignee
// is a raw user UUID and BuildNumber may be null for runs that never reported
// one.
type UserJobRun struct {
	ID                  string `json:"id"`
	TestID              string `json:"test_id"`
	ReleaseID           string `json:"release_id"`
	GroupID             string `json:"group_id"`
	BuildID             string `json:"build_id"`
	BuildNumber         *int   `json:"build_number"`
	BuildJobURL         string `json:"build_job_url"`
	StartTime           string `json:"start_time"`
	Status              string `json:"status"`
	InvestigationStatus string `json:"investigation_status"`
	Assignee            string `json:"assignee"`
	ScyllaVersion       string `json:"scylla_version"`
}

// PlannedLastRun is the subset of the last run document embedded in a
// planned-jobs row that the CLI displays. The backend returns the whole run
// document; unknown fields are ignored on decode.
type PlannedLastRun struct {
	ID                  string `json:"id"`
	TestID              string `json:"test_id"`
	BuildID             string `json:"build_id"`
	BuildNumber         *int   `json:"build_number"`
	BuildJobURL         string `json:"build_job_url"`
	StartTime           string `json:"start_time"`
	Status              string `json:"status"`
	InvestigationStatus string `json:"investigation_status"`
	Assignee            string `json:"assignee"`
	ScyllaVersion       string `json:"scylla_version"`
}

// PlannedTest is one row of GET /api/v1/user/planned_jobs (and the team
// variant): an enabled test the user is expected to execute according to the
// release plans they own or participate in, with its most recent run or nil.
type PlannedTest struct {
	ID             string          `json:"id"`
	Name           string          `json:"name"`
	PrettyName     string          `json:"pretty_name"`
	BuildSystemID  string          `json:"build_system_id"`
	BuildSystemURL string          `json:"build_system_url"`
	PluginName     string          `json:"plugin_name"`
	LastRun        *PlannedLastRun `json:"last_run"`
}

// JobSummary is the per-job row printed by `my-jobs`. The JSON fields mirror the
// text columns exactly so both output modes carry the same data. ID is the run
// UUID; for planned tests it is the last run's id and empty when the test never
// ran, in which case BuildNumber is nil and Status is "not_run".
type JobSummary struct {
	ID                  string `json:"id"`
	BuildID             string `json:"build_id"`
	BuildNumber         *int   `json:"build_number"`
	Version             string `json:"version"`
	BuildJobURL         string `json:"build_job_url"`
	ArgusURL            string `json:"argus_url"`
	Status              string `json:"status"`
	InvestigationStatus string `json:"investigation_status"`
	Assignee            string `json:"assignee"`
}

// Headers implements output.Tabular for JobSummary.
func (JobSummary) Headers() []string {
	return []string{"Id", "Build Id", "Build Number", "Version", "Build Job URL", "Argus URL", "Status", "Investigation Status", "Assignee"}
}

// Rows implements output.Tabular for JobSummary.
func (j JobSummary) Rows() [][]string {
	number := ""
	if j.BuildNumber != nil {
		number = strconv.Itoa(*j.BuildNumber)
	}
	return [][]string{{
		j.ID,
		j.BuildID,
		number,
		j.Version,
		j.BuildJobURL,
		j.ArgusURL,
		j.Status,
		j.InvestigationStatus,
		j.Assignee,
	}}
}

// JobSummaries is a slice of job summaries rendered as one row per job in text
// output, while JSON marshalling emits the full slice. It backs every `my-jobs`
// output.
type JobSummaries []JobSummary

// Headers implements output.Tabular for JobSummaries.
func (JobSummaries) Headers() []string { return JobSummary{}.Headers() }

// Rows implements output.Tabular for JobSummaries.
func (js JobSummaries) Rows() [][]string {
	rows := make([][]string, 0, len(js))
	for _, j := range js {
		rows = append(rows, j.Rows()[0])
	}
	return rows
}
