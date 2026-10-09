package models

import (
	"encoding/json"
	"strconv"
)

// Issue is a unified display model for both GitHub and Jira issues returned by
// the /issues/get endpoint. The Key field is synthesized: owner/repo#number for
// GitHub issues, or the Jira issue key.
type Issue struct {
	Key     string `json:"key"`
	Subtype string `json:"subtype"`
	Title   string `json:"title"`
	State   string `json:"state"`
	URL     string `json:"url"`
}

// ParseIssues converts raw JSON issue objects (which may be GitHub or Jira
// flavored) into a unified slice of Issue for tabular display.
func ParseIssues(raw []json.RawMessage) []Issue {
	issues := make([]Issue, 0, len(raw))
	for _, r := range raw {
		var m map[string]json.RawMessage
		if err := json.Unmarshal(r, &m); err != nil {
			continue
		}

		var issue Issue
		issue.Subtype = unquote(m["subtype"])
		issue.State = unquote(m["state"])

		switch issue.Subtype {
		case "github":
			owner := unquote(m["owner"])
			repo := unquote(m["repo"])
			var number json.Number
			_ = json.Unmarshal(m["number"], &number)
			issue.Key = owner + "/" + repo + "#" + number.String()
			issue.Title = unquote(m["title"])
			issue.URL = unquote(m["url"])
		case "jira":
			issue.Key = unquote(m["key"])
			issue.Title = unquote(m["summary"])
			issue.URL = unquote(m["permalink"])
		default:
			issue.Title = unquote(m["title"])
			issue.URL = unquote(m["url"])
		}

		issues = append(issues, issue)
	}
	return issues
}

// unquote removes surrounding quotes from a raw JSON string value.
func unquote(raw json.RawMessage) string {
	var s string
	if raw == nil {
		return ""
	}
	_ = json.Unmarshal(raw, &s)
	return s
}

// LinkedRun holds the fields of one element of the links list returned by
// GET /api/v1/issues/{key}/links that a run summary row reads. URL is the
// absolute Argus run page link built by the server.
type LinkedRun struct {
	RunID          string `json:"run_id"`
	TestName       string `json:"test_name"`
	Status         string `json:"status"`
	StartTime      string `json:"start_time"`
	BuildID        string `json:"build_id"`
	BuildNumber    *int   `json:"build_number"`
	ScyllaVersion  string `json:"scylla_version"`
	ProductVersion string `json:"product_version"`
	URL            string `json:"url"`
}

// Version is the run's Scylla version, or its product version when the run
// reports no Scylla version.
func (l LinkedRun) Version() string {
	if l.ScyllaVersion != "" {
		return l.ScyllaVersion
	}
	return l.ProductVersion
}

// IssueLinks is the payload of GET /api/v1/issues/{key}/links. Links is
// ordered newest run first.
type IssueLinks struct {
	Links []LinkedRun `json:"links"`
	raw   RawJSON
}

// UnmarshalJSON decodes the links and keeps the payload for [IssueLinks.Raw].
func (l *IssueLinks) UnmarshalJSON(b []byte) error {
	type plain IssueLinks
	if err := json.Unmarshal(b, (*plain)(l)); err != nil {
		return err
	}
	l.raw = append(RawJSON(nil), b...)
	return nil
}

// Raw returns the payload exactly as the API sent it: the issue, or null for a
// key Argus does not hold, and every field of every link.
func (l IssueLinks) Raw() RawJSON { return l.raw }

// Summaries maps every link to its display row, keeping the server order. The
// result is never nil, so an issue without links marshals to an empty array.
func (l IssueLinks) Summaries() IssueRunSummaries {
	out := make(IssueRunSummaries, 0, len(l.Links))
	for _, link := range l.Links {
		out = append(out, IssueRunSummary{
			ID:          link.RunID,
			Test:        link.TestName,
			BuildID:     link.BuildID,
			BuildNumber: link.BuildNumber,
			Version:     link.Version(),
			Status:      link.Status,
			StartTime:   link.StartTime,
			ArgusURL:    link.URL,
		})
	}
	return out
}

// IssueRunSummary is the per-run row printed by `issue runs`. The JSON fields
// mirror the text columns exactly, and the fields it shares with [JobSummary]
// keep the same names.
type IssueRunSummary struct {
	ID          string `json:"id"`
	Test        string `json:"test"`
	BuildID     string `json:"build_id"`
	BuildNumber *int   `json:"build_number"`
	Version     string `json:"version"`
	Status      string `json:"status"`
	StartTime   string `json:"start_time"`
	ArgusURL    string `json:"argus_url"`
}

// Headers implements output.Tabular for IssueRunSummary.
func (IssueRunSummary) Headers() []string {
	return []string{"Id", "Test", "Build Id", "Build Number", "Version", "Status", "Start Time", "Argus URL"}
}

// Rows implements output.Tabular for IssueRunSummary.
func (r IssueRunSummary) Rows() [][]string {
	number := ""
	if r.BuildNumber != nil {
		number = strconv.Itoa(*r.BuildNumber)
	}
	return [][]string{{
		r.ID,
		r.Test,
		r.BuildID,
		number,
		r.Version,
		r.Status,
		r.StartTime,
		r.ArgusURL,
	}}
}

// IssueRunSummaries is a slice of run summaries rendered as one row per run in
// text output, while JSON marshalling emits the full slice. It backs the
// default `issue runs` output.
type IssueRunSummaries []IssueRunSummary

// Headers implements output.Tabular for IssueRunSummaries.
func (IssueRunSummaries) Headers() []string { return IssueRunSummary{}.Headers() }

// Rows implements output.Tabular for IssueRunSummaries.
func (rs IssueRunSummaries) Rows() [][]string {
	rows := make([][]string, 0, len(rs))
	for _, r := range rs {
		rows = append(rows, r.Rows()[0])
	}
	return rows
}
