package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTriggeredBuilds_Rows(t *testing.T) {
	builds := models.TriggeredBuilds{
		{
			Test:          "Tier 1/longevity-100gb",
			BuildSystemID: "scylla-2026.2/longevity/longevity-100gb",
			QueueItem:     101,
			URL:           "https://jenkins/job/longevity/42/",
			ArgusURL:      "https://argus/test/scylla-2026.2/longevity/longevity-100gb/42",
			Status:        "started",
		},
		{Test: "Tier 1/other", BuildSystemID: "scylla-2026.2/other", Status: "error: boom"},
	}

	assert.Equal(t,
		[]string{"Test", "Build System ID", "Queue Item", "URL", "Argus URL", "Status"},
		builds.Headers(),
	)
	assert.Equal(t, [][]string{
		{
			"Tier 1/longevity-100gb",
			"scylla-2026.2/longevity/longevity-100gb",
			"101",
			"https://jenkins/job/longevity/42/",
			"https://argus/test/scylla-2026.2/longevity/longevity-100gb/42",
			"started",
		},
		{"Tier 1/other", "scylla-2026.2/other", "", "", "", "error: boom"},
	}, builds.Rows())
}

func TestStartedBuild_MarshalJSON(t *testing.T) {
	b := models.StartedBuild{
		BuildID:     "scylla-2026.2/longevity/longevity-100gb",
		JenkinsURL:  "https://jenkins/job/longevity/42/",
		BuildNumber: 42,
		ArgusURL:    "https://argus/test/scylla-2026.2/longevity/longevity-100gb/42",
	}
	raw, err := json.Marshal(b)
	require.NoError(t, err)

	var back map[string]any
	require.NoError(t, json.Unmarshal(raw, &back))
	assert.Equal(t, "scylla-2026.2/longevity/longevity-100gb", back["build_id"])
	assert.Equal(t, float64(42), back["build_number"])
	assert.Equal(t, "https://argus/test/scylla-2026.2/longevity/longevity-100gb/42", back["argus_url"])
}

func TestStartedBuild_MarshalJSON_OmitsEmpty(t *testing.T) {
	// Before the build number is known, optional fields are omitted.
	raw, err := json.Marshal(models.StartedBuild{BuildID: "scylla-2026.2/other"})
	require.NoError(t, err)

	var back map[string]any
	require.NoError(t, json.Unmarshal(raw, &back))
	_, hasNumber := back["build_number"]
	assert.False(t, hasNumber)
	_, hasArgus := back["argus_url"]
	assert.False(t, hasArgus)
}

func TestExecutedBuild_MarshalJSON(t *testing.T) {
	b := models.ExecutedBuild{
		BuildID:     "scylla-2026.2/longevity/longevity-100gb",
		QueueItem:   101,
		BuildNumber: 43,
		ArgusURL:    "https://argus/test/scylla-2026.2/longevity/longevity-100gb/43",
	}
	raw, err := json.Marshal(b)
	require.NoError(t, err)

	var back map[string]any
	require.NoError(t, json.Unmarshal(raw, &back))
	assert.Equal(t, "scylla-2026.2/longevity/longevity-100gb", back["build_id"])
	assert.Equal(t, float64(101), back["queue_item"])
	assert.Equal(t, float64(43), back["build_number"])
	assert.Equal(t, "https://argus/test/scylla-2026.2/longevity/longevity-100gb/43", back["argus_url"])
}

func TestExecutedBuild_MarshalJSON_OmitsGuessWhenUnknown(t *testing.T) {
	// The queue item is always present; the guessed number/link are omitted
	// when the backend couldn't resolve the next build number.
	raw, err := json.Marshal(models.ExecutedBuild{BuildID: "scylla-2026.2/other", QueueItem: 7})
	require.NoError(t, err)

	var back map[string]any
	require.NoError(t, json.Unmarshal(raw, &back))
	assert.Equal(t, float64(7), back["queue_item"])
	_, hasNumber := back["build_number"]
	assert.False(t, hasNumber)
	_, hasArgus := back["argus_url"]
	assert.False(t, hasArgus)
}

func TestJenkinsBuildResponse_DecodesNextBuildNumber(t *testing.T) {
	var resp models.JenkinsBuildResponse
	require.NoError(t, json.Unmarshal([]byte(`{"queueItem":101,"nextBuildNumber":43}`), &resp))
	assert.Equal(t, 101, resp.QueueItem)
	assert.Equal(t, 43, resp.NextBuildNumber)

	// Absent nextBuildNumber decodes to 0 (guess unavailable).
	var noGuess models.JenkinsBuildResponse
	require.NoError(t, json.Unmarshal([]byte(`{"queueItem":5}`), &noGuess))
	assert.Equal(t, 5, noGuess.QueueItem)
	assert.Zero(t, noGuess.NextBuildNumber)
}
