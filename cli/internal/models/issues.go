package models

import "encoding/json"

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
