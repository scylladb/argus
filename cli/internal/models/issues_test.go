package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func strPtr(s string) *string { return &s }

func TestIssueLinks_Summaries(t *testing.T) {
	t.Parallel()
	links := models.IssueLinks{
		Issue: map[string]any{"key": "SCT-1234"},
		Links: []models.LinkedRun{
			{
				RunID: "run-2", TestID: "test-1", TestName: "longevity-100gb-4h", PluginName: "scylla-cluster-tests",
				Status: "failed", StartTime: "2026-09-30T22:10:44.000Z", BuildID: "rel/g/longevity-100gb-4h",
				BuildNumber: intPtr(412), ScyllaVersion: strPtr("2026.2.0~dev"), ProductVersion: strPtr("2026.2.0"),
				LinkedOn: strPtr("2026-10-01T07:02:13.540Z"), URL: "https://argus/test/rel/g/longevity-100gb-4h/412",
			},
			{RunID: "run-1", TestName: "artifacts-ubuntu", BuildID: "rel/g/artifacts-ubuntu", Status: "passed"},
		},
	}

	got := links.Summaries()

	require.Len(t, got, 2)
	assert.Equal(t, models.IssueRunSummary{
		ID: "run-2", Test: "longevity-100gb-4h", BuildID: "rel/g/longevity-100gb-4h", BuildNumber: intPtr(412),
		Version: "2026.2.0~dev", Status: "failed", StartTime: "2026-09-30T22:10:44.000Z",
		ArgusURL: "https://argus/test/rel/g/longevity-100gb-4h/412",
	}, got[0])
	assert.Equal(t, "run-1", got[1].ID)
	assert.Nil(t, got[1].BuildNumber)
}

func TestIssueLinks_Summaries_Version(t *testing.T) {
	t.Parallel()
	links := models.IssueLinks{Links: []models.LinkedRun{
		{RunID: "scylla", ScyllaVersion: strPtr("2026.2.0~dev"), ProductVersion: strPtr("2026.2.0")},
		{RunID: "product-only", ProductVersion: strPtr("2026.2.0")},
		{RunID: "empty-scylla", ScyllaVersion: strPtr(""), ProductVersion: strPtr("2026.2.0")},
		{RunID: "none"},
	}}

	got := links.Summaries()

	require.Len(t, got, 4)
	assert.Equal(t, "2026.2.0~dev", got[0].Version)
	assert.Equal(t, "2026.2.0", got[1].Version)
	assert.Equal(t, "2026.2.0", got[2].Version)
	assert.Equal(t, "", got[3].Version)
}

func TestLinkedRun_KeepsNulls(t *testing.T) {
	t.Parallel()
	in := `{"run_id":"r","test_id":"t","test_name":"n","plugin_name":"generic","status":"passed",
		"start_time":"2026-09-28T10:00:00.000Z","build_id":"b","build_number":null,"scylla_version":null,
		"product_version":null,"linked_on":null,"url":"u"}`
	var run models.LinkedRun
	require.NoError(t, json.Unmarshal([]byte(in), &run))

	out, err := json.Marshal(run)

	require.NoError(t, err)
	assert.JSONEq(t, in, string(out))
}

func TestIssueLinks_KeepsIssueNumbers(t *testing.T) {
	t.Parallel()
	in := `{"issue":{"key":"SCYLLADB-3959","labels":[{"id":3903313650,"name":"repair"}]},
		"links":[{"run_id":"r","build_number":26}]}`
	var links models.IssueLinks
	require.NoError(t, json.Unmarshal([]byte(in), &links))

	assert.Contains(t, models.NewKVTabular(links).Rows(), []string{"issue.labels.0.id", "3903313650"})
	require.Len(t, links.Links, 1)
	require.NotNil(t, links.Links[0].BuildNumber)
	assert.Equal(t, 26, *links.Links[0].BuildNumber)
	out, err := json.Marshal(links)
	require.NoError(t, err)
	assert.Contains(t, string(out), `"id":3903313650`)
}

func TestIssueLinks_Summaries_Empty(t *testing.T) {
	t.Parallel()
	raw, err := json.Marshal(models.IssueLinks{}.Summaries())
	require.NoError(t, err)
	assert.JSONEq(t, `[]`, string(raw))
}

func TestIssueRunSummaries_Rows(t *testing.T) {
	t.Parallel()
	rows := models.IssueRunSummaries{
		{
			ID: "run-2", Test: "longevity-100gb-4h", BuildID: "rel/g/longevity-100gb-4h", BuildNumber: intPtr(412),
			Version: "2026.2.0~dev", Status: "failed", StartTime: "2026-09-30T22:10:44.000Z", ArgusURL: "https://argus/x/412",
		},
		{ID: "run-1", BuildID: "rel/g/artifacts-ubuntu", Status: "passed"},
	}
	var _ output.Tabular = rows

	assert.Equal(t, []string{"Id", "Test", "Build Id", "Build Number", "Version", "Status", "Start Time", "Argus URL"}, rows.Headers())
	require.Len(t, rows.Rows(), 2)
	assert.Equal(t, []string{
		"run-2", "longevity-100gb-4h", "rel/g/longevity-100gb-4h", "412", "2026.2.0~dev", "failed",
		"2026-09-30T22:10:44.000Z", "https://argus/x/412",
	}, rows.Rows()[0])
	assert.Equal(t, "", rows.Rows()[1][3])
}
