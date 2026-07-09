package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestQueueStatuses_Rows(t *testing.T) {
	statuses := models.QueueStatuses{
		{QueueItem: 10, Status: "started", URL: "https://ci/job/42/", Number: 42},
		{QueueItem: 11, Status: "pending", Why: "Waiting for next available executor"},
	}

	assert.Equal(t, []string{"Queue Item", "Status", "URL", "Number", "Why"}, statuses.Headers())
	assert.Equal(t, [][]string{
		{"10", "started", "https://ci/job/42/", "42", ""},
		{"11", "pending", "", "", "Waiting for next available executor"},
	}, statuses.Rows())
}

func TestQueueStatuses_MarshalJSON(t *testing.T) {
	statuses := models.QueueStatuses{
		{QueueItem: 10, Status: "started", URL: "https://ci/job/42/", Number: 42},
		{QueueItem: 11, Status: "pending", Why: "queued"},
	}

	raw, err := json.Marshal(statuses)
	require.NoError(t, err)

	var back []map[string]any
	require.NoError(t, json.Unmarshal(raw, &back))
	require.Len(t, back, 2)
	assert.Equal(t, float64(10), back[0]["queue_item"])
	assert.Equal(t, "started", back[0]["status"])
	// Zero-valued optional fields are omitted for the pending row.
	_, hasURL := back[1]["url"]
	assert.False(t, hasURL)
	_, hasNumber := back[1]["number"]
	assert.False(t, hasNumber)
}
