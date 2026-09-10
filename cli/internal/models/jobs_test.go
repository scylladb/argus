package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func intPtr(n int) *int { return &n }

func TestJobSummary_HeadersAndRowsAlign(t *testing.T) {
	t.Parallel()
	row := models.JobSummary{
		ID: "run-1", BuildID: "rel/g/t", BuildNumber: intPtr(42), Version: "2026.2.0~dev", BuildJobURL: "https://jenkins/job/t/42/",
		ArgusURL: "https://argus/test/rel/g/t/42", Status: "failed",
		InvestigationStatus: "not_investigated", Assignee: "alice",
	}
	headers := row.Headers()
	rows := row.Rows()
	require.Len(t, rows, 1)
	assert.Len(t, rows[0], len(headers))
	assert.Equal(t, []string{"Id", "Build Id", "Build Number", "Version", "Build Job URL", "Argus URL", "Status", "Investigation Status", "Assignee"}, headers)
	assert.Equal(t, []string{"run-1", "rel/g/t", "42", "2026.2.0~dev", "https://jenkins/job/t/42/", "https://argus/test/rel/g/t/42", "failed", "not_investigated", "alice"}, rows[0])
}

func TestJobSummary_NilBuildNumberRendersEmpty(t *testing.T) {
	t.Parallel()
	row := models.JobSummary{BuildID: "rel/g/t", Status: "not_run"}
	assert.Equal(t, "", row.Rows()[0][2])

	raw, err := json.Marshal(row)
	require.NoError(t, err)
	assert.Contains(t, string(raw), `"build_number":null`)
}

func TestJobSummaries_OneRowPerJob(t *testing.T) {
	t.Parallel()
	js := models.JobSummaries{{BuildID: "a"}, {BuildID: "b"}}
	var _ output.Tabular = js
	assert.Equal(t, models.JobSummary{}.Headers(), js.Headers())
	rows := js.Rows()
	require.Len(t, rows, 2)
	assert.Equal(t, "a", rows[0][1])
	assert.Equal(t, "b", rows[1][1])
}

func TestUserJobRun_DecodesBackendRow(t *testing.T) {
	t.Parallel()
	raw := `{"build_id":"rel/g/t","start_time":"2026-08-30T12:04:11.123Z","release_id":"rl","group_id":"gr",
		"assignee":"u1","test_id":"tt","id":"rr","status":"failed","investigation_status":"not_investigated",
		"build_job_url":"https://jenkins/job/t/42/","build_number":42,"scylla_version":"2026.2.0~dev"}`
	var run models.UserJobRun
	require.NoError(t, json.Unmarshal([]byte(raw), &run))
	assert.Equal(t, "rel/g/t", run.BuildID)
	require.NotNil(t, run.BuildNumber)
	assert.Equal(t, 42, *run.BuildNumber)
	assert.Equal(t, "2026.2.0~dev", run.ScyllaVersion)
}

func TestPlannedTest_DecodesNullAndFullLastRun(t *testing.T) {
	t.Parallel()
	raw := `[{"id":"t1","name":"a","build_system_id":"rel/g/a","build_system_url":"https://jenkins/job/a/","last_run":null},
		{"id":"t2","name":"b","build_system_id":"rel/g/b","last_run":{"id":"r","build_id":"rel/g/b","build_number":7,
		"status":"passed","investigation_status":"investigated","assignee":"u1","scylla_version":"2026.1.3","logs":[],"heartbeat":1,"sct_runner_host":{"x":1}}}]`
	var tests []models.PlannedTest
	require.NoError(t, json.Unmarshal([]byte(raw), &tests))
	require.Len(t, tests, 2)
	assert.Nil(t, tests[0].LastRun)
	require.NotNil(t, tests[1].LastRun)
	assert.Equal(t, 7, *tests[1].LastRun.BuildNumber)
	assert.Equal(t, "investigated", tests[1].LastRun.InvestigationStatus)
	assert.Equal(t, "2026.1.3", tests[1].LastRun.ScyllaVersion)
}
