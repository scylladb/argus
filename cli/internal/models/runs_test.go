package models_test

import (
	"encoding/json"
	"strings"
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

func marshalEvents(t *testing.T, resp models.SCTEventsResponse) []map[string]any {
	t.Helper()
	raw, err := json.Marshal(resp)
	require.NoError(t, err)
	var got []map[string]any
	require.NoError(t, json.Unmarshal(raw, &got))
	return got
}

func TestSCTEventsResponseJSONPrefersSummary(t *testing.T) {
	got := marshalEvents(t, models.SCTEventsResponse{
		RunID: "run-1",
		Events: []models.SCTEvent{
			{EventID: "e1", Message: "full text", Summary: "short text"},
			{EventID: "e2", Message: "full text"},
			{EventID: "e3"},
		},
	})
	require.Len(t, got, 3)

	assert.Equal(t, "short text", got[0]["summary"])
	assert.NotContains(t, got[0], "message")
	assert.Equal(t, "e1", got[0]["event_id"])

	assert.Equal(t, "full text", got[1]["message"])
	assert.NotContains(t, got[1], "summary")

	assert.Contains(t, got[2], "message")
	assert.NotContains(t, got[2], "summary")
}

func TestSCTEventsResponseJSONRaw(t *testing.T) {
	got := marshalEvents(t, models.SCTEventsResponse{
		RunID: "run-1",
		Raw:   true,
		Events: []models.SCTEvent{
			{EventID: "e1", Message: "full text", Summary: "short text"},
			{EventID: "e2", Message: "full text"},
		},
	})
	require.Len(t, got, 2)
	for _, e := range got {
		assert.Equal(t, "full text", e["message"])
		assert.NotContains(t, e, "summary")
	}
}

func TestSCTEventsResponseRows(t *testing.T) {
	long := strings.Repeat("x", 250)
	events := []models.SCTEvent{
		{EventID: "e1", Message: "full text", Summary: "short text"},
		{EventID: "e2", Message: "full text"},
		{EventID: "e3", Message: "full text", Summary: long},
	}
	tests := []struct {
		name string
		raw  bool
		want []string
	}{
		{"summary by default", false, []string{"short text", "full text", long[:200] + "..."}},
		{"message with raw", true, []string{"full text", "full text", "full text"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp := models.SCTEventsResponse{Events: events, Raw: tt.raw}
			headers := resp.Headers()
			require.Len(t, headers, 7)
			assert.Equal(t, "Message", headers[6])

			rows := resp.Rows()
			require.Len(t, rows, len(tt.want))
			for i, row := range rows {
				require.Len(t, row, 7)
				assert.Equal(t, tt.want[i], row[6])
			}
		})
	}
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
