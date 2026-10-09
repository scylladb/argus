package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestIssueLinks_Summaries(t *testing.T) {
	t.Parallel()
	links := models.IssueLinks{
		Links: []models.LinkedRun{
			{
				RunID: "run-2", TestName: "longevity-100gb-4h", Status: "failed", StartTime: "2026-09-30T22:10:44.000Z",
				BuildID: "rel/g/longevity-100gb-4h", BuildNumber: intPtr(412), ScyllaVersion: "2026.2.0~dev",
				ProductVersion: "2026.2.0", URL: "https://argus/test/rel/g/longevity-100gb-4h/412",
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
		{RunID: "scylla", ScyllaVersion: "2026.2.0~dev", ProductVersion: "2026.2.0"},
		{RunID: "product-only", ProductVersion: "2026.2.0"},
		{RunID: "none"},
	}}

	got := links.Summaries()

	require.Len(t, got, 3)
	assert.Equal(t, "2026.2.0~dev", got[0].Version)
	assert.Equal(t, "2026.2.0", got[1].Version)
	assert.Equal(t, "", got[2].Version)
}

func TestIssueLinks_Raw(t *testing.T) {
	t.Parallel()
	in := `{"issue":{"key":"SCYLLADB-3959","labels":[{"id":3903313650}]},"links":[{"run_id":"r","build_number":26,` +
		`"scylla_version":null,"product_version":"2026.2.0","linked_on":null,"added_later":"kept"}]}`
	var links models.IssueLinks
	require.NoError(t, json.Unmarshal([]byte(in), &links))

	assert.Equal(t, in, string(links.Raw()))
	require.Len(t, links.Links, 1)
	require.NotNil(t, links.Links[0].BuildNumber)
	assert.Equal(t, 26, *links.Links[0].BuildNumber)
	assert.Equal(t, "2026.2.0", links.Links[0].Version())
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
