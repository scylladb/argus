package models

import (
	"fmt"
	"strconv"
	"time"
)

// ResultTableSummary is one generic result table name of a release.
type ResultTableSummary struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Columns     []string `json:"columns"`
	Tests       int      `json:"tests"`
}

// ResultTableSummaries is the response of the release tables endpoint.
type ResultTableSummaries []ResultTableSummary

func (s ResultTableSummaries) Headers() []string {
	return []string{"Table", "Tests", "Columns"}
}

func (s ResultTableSummaries) Rows() [][]string {
	rows := make([][]string, 0, len(s))
	for _, table := range s {
		rows = append(rows, []string{table.Name, strconv.Itoa(table.Tests), fmt.Sprint(table.Columns)})
	}
	return rows
}

// ReleaseResultCell is one row and column value of a generic result table.
type ReleaseResultCell struct {
	Row    string `json:"row"`
	Column string `json:"column"`
	Value  any    `json:"value"`
	Status string `json:"status"`
}

// ResultRun holds the cells that one run submitted to a table.
type ResultRun struct {
	RunID         string              `json:"run_id"`
	BuildNumber   *int                `json:"build_number"`
	ScyllaVersion string              `json:"scylla_version"`
	SubmittedAt   time.Time           `json:"submitted_at"`
	SUTTimestamp  *time.Time          `json:"sut_timestamp"`
	Cells         []ReleaseResultCell `json:"cells"`
}

// ResultTest holds the runs of one test for a table.
type ResultTest struct {
	TestID   string `json:"test_id"`
	TestName string `json:"test_name"`
	BuildID  string `json:"build_id"`
	// RunsTruncated is true when the test has more runs in the window than the server returns.
	RunsTruncated bool        `json:"runs_truncated"`
	Runs          []ResultRun `json:"runs"`
}

// ResultGroup holds the results of one table across the tests of a release.
type ResultGroup struct {
	Table       string       `json:"table"`
	Description string       `json:"description"`
	Tests       []ResultTest `json:"tests"`
}

// ResultGroups is the response of the release results endpoint.
type ResultGroups []ResultGroup

func (g ResultGroups) Headers() []string {
	return []string{"Table", "Build ID", "Build", "Run ID", "Submitted", "Row", "Column", "Value", "Status"}
}

func (g ResultGroups) Rows() [][]string {
	var rows [][]string
	for _, group := range g {
		for _, test := range group.Tests {
			for _, run := range test.Runs {
				for _, cell := range run.Cells {
					rows = append(rows, []string{
						group.Table, test.BuildID, buildNumber(run.BuildNumber), run.RunID, run.SubmittedAt.Format(time.RFC3339),
						cell.Row, cell.Column, fmt.Sprint(cell.Value), cell.Status,
					})
				}
			}
		}
	}
	return rows
}

func buildNumber(n *int) string {
	if n == nil {
		return ""
	}
	return strconv.Itoa(*n)
}
