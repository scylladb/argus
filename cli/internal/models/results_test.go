package models

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestResultGroupsRows(t *testing.T) {
	build := 412
	submitted := time.Date(2026, 10, 20, 8, 12, 0, 0, time.UTC)
	groups := ResultGroups{{
		Table: "throughput",
		Tests: []ResultTest{{
			BuildID: "scylla-master/longevity-cdc",
			Runs: []ResultRun{
				{RunID: "r1", BuildNumber: &build, StartedAt: submitted, Cells: []ReleaseResultCell{
					{Row: "write", Column: "ops", Value: 1200.5, Status: "PASS"},
					{Row: "read", Column: "ops", Value: "n/a", Status: "UNSET"},
				}},
				{RunID: "r2", StartedAt: submitted, Cells: []ReleaseResultCell{
					{Row: "write", Column: "ops", Value: 900.0, Status: "ERROR"},
				}},
			},
		}},
	}}

	assert.Len(t, groups.Headers(), 9)
	assert.Equal(t, [][]string{
		{"throughput", "scylla-master/longevity-cdc", "412", "r1", "2026-10-20T08:12:00Z", "write", "ops", "1200.5", "PASS"},
		{"throughput", "scylla-master/longevity-cdc", "412", "r1", "2026-10-20T08:12:00Z", "read", "ops", "n/a", "UNSET"},
		{"throughput", "scylla-master/longevity-cdc", "", "r2", "2026-10-20T08:12:00Z", "write", "ops", "900", "ERROR"},
	}, groups.Rows())
}

func TestResultTableSummariesRows(t *testing.T) {
	tables := ResultTableSummaries{{Name: "latency", Columns: []string{"p99", "p50"}, Tests: 3}}

	assert.Equal(t, []string{"Table", "Tests", "Columns"}, tables.Headers())
	assert.Equal(t, [][]string{{"latency", "3", "[p99 p50]"}}, tables.Rows())
}
