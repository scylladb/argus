package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSCTEventDecodeSummary(t *testing.T) {
	tests := []struct {
		name string
		body string
		want string
	}{
		{"with summary", `{"event_id":"e1","message":"full text","summary":"short text"}`, "short text"},
		{"null summary", `{"event_id":"e1","message":"full text","summary":null}`, ""},
		{"no summary key", `{"event_id":"e1","message":"full text"}`, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var e models.SCTEvent
			require.NoError(t, json.Unmarshal([]byte(tt.body), &e))
			assert.Equal(t, tt.want, e.Summary)
			assert.Equal(t, "full text", e.Message)
		})
	}
}

func TestSCTEventsResponseJSONSummary(t *testing.T) {
	resp := models.SCTEventsResponse{
		RunID: "run-1",
		Events: []models.SCTEvent{
			{EventID: "e1", Message: "full text", Summary: "short text"},
			{EventID: "e2", Message: "full text"},
		},
	}
	raw, err := json.Marshal(resp)
	require.NoError(t, err)

	var got []map[string]any
	require.NoError(t, json.Unmarshal(raw, &got))
	require.Len(t, got, 2)
	assert.Equal(t, "short text", got[0]["summary"])
	assert.Equal(t, "full text", got[0]["message"])
	assert.NotContains(t, got[1], "summary")
}

func TestSCTEventsResponseRowsSummary(t *testing.T) {
	resp := models.SCTEventsResponse{
		Events: []models.SCTEvent{
			{EventID: "e1", Message: "full text", Summary: "short text"},
			{EventID: "e2", Message: "full text"},
		},
	}
	require.Equal(t, "Summary", resp.Headers()[len(resp.Headers())-1])

	rows := resp.Rows()
	require.Len(t, rows, 2)
	assert.Equal(t, []string{"full text", "short text"}, rows[0][len(rows[0])-2:])
	assert.Equal(t, []string{"full text", ""}, rows[1][len(rows[1])-2:])
}

func TestNemesisRunInfoDecodeDescription(t *testing.T) {
	tests := []struct {
		name string
		body string
		want string
	}{
		{"with description", `{"name":"n","description":"Kill a node"}`, "Kill a node"},
		{"null description", `{"name":"n","description":null}`, ""},
		{"no description key", `{"name":"n"}`, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var nem models.NemesisRunInfo
			require.NoError(t, json.Unmarshal([]byte(tt.body), &nem))
			assert.Equal(t, tt.want, nem.Description)
			assert.Equal(t, "n", nem.Name)
		})
	}
}

func TestNemesisResponseRowsWithoutDescriptionFlag(t *testing.T) {
	resp := models.NewNemesisResponse("run-1", []models.NemesisRunInfo{
		{ClassName: "C", Name: "n", Description: "Kill a node"},
	}, false)

	headers := resp.Headers()
	require.Len(t, headers, 8)
	assert.Equal(t, "Stack Trace", headers[len(headers)-1])
	rows := resp.Rows()
	require.Len(t, rows, 1)
	assert.Len(t, rows[0], 8)
}

func TestNemesisResponseRowsWithDescriptionFlag(t *testing.T) {
	resp := models.NewNemesisResponse("run-1", []models.NemesisRunInfo{
		{ClassName: "C", Name: "n", Description: "Kill a node"},
	}, true)

	headers := resp.Headers()
	require.Len(t, headers, 9)
	assert.Equal(t, "Description", headers[8])
	rows := resp.Rows()
	require.Len(t, rows, 1)
	require.Len(t, rows[0], 9)
	assert.Equal(t, "Kill a node", rows[0][8])
}

func TestNemesisResponseMarshalJSONCarriesDescription(t *testing.T) {
	resp := models.NewNemesisResponse("run-1", []models.NemesisRunInfo{
		{ClassName: "C", Name: "n", Description: "Kill a node"},
	}, false)

	raw, err := json.Marshal(resp)
	require.NoError(t, err)
	var got []map[string]any
	require.NoError(t, json.Unmarshal(raw, &got))
	require.Len(t, got, 1)
	assert.Equal(t, "Kill a node", got[0]["description"])
}
