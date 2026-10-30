package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDeduplicateEvents(t *testing.T) {
	tests := []struct {
		name       string
		events     []models.SCTEvent
		wantCount  int
		wantChecks func(t *testing.T, result []models.SCTEvent)
	}{
		{
			name:      "empty input",
			events:    nil,
			wantCount: 0,
		},
		{
			name: "no duplicates passthrough",
			events: []models.SCTEvent{
				{EventID: "a", Ts: "2024-01-01T00:00:00Z", EventType: "X"},
				{EventID: "b", Ts: "2024-01-01T01:00:00Z", EventType: "Y"},
			},
			wantCount: 2,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				for _, e := range result {
					if len(e.RepeatedAt) != 0 {
						t.Errorf("event %s: expected no RepeatedAt, got %v", e.EventID, e.RepeatedAt)
					}
				}
			},
		},
		{
			name: "simple dedup with original present",
			events: []models.SCTEvent{
				{EventID: "orig", Ts: "2024-01-01T00:00:00Z", EventType: "X"},
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "orig"},
				{EventID: "d2", Ts: "2024-01-01T02:00:00Z", DuplicateID: "orig"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				if result[0].EventID != "orig" {
					t.Fatalf("expected original event, got %s", result[0].EventID)
				}
				if len(result[0].RepeatedAt) != 2 {
					t.Fatalf("expected 2 repeats, got %d", len(result[0].RepeatedAt))
				}
				if result[0].RepeatedAt[0] != "2024-01-01T01:00:00Z" {
					t.Errorf("repeat[0] = %s, want 2024-01-01T01:00:00Z", result[0].RepeatedAt[0])
				}
				if result[0].RepeatedAt[1] != "2024-01-01T02:00:00Z" {
					t.Errorf("repeat[1] = %s, want 2024-01-01T02:00:00Z", result[0].RepeatedAt[1])
				}
			},
		},
		{
			name: "orphaned duplicates promote earliest",
			events: []models.SCTEvent{
				{EventID: "d2", Ts: "2024-01-01T03:00:00Z", DuplicateID: "missing-orig", EventType: "X"},
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "missing-orig", EventType: "X"},
				{EventID: "d3", Ts: "2024-01-01T05:00:00Z", DuplicateID: "missing-orig", EventType: "X"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				promoted := result[0]
				if promoted.EventID != "d1" {
					t.Fatalf("expected earliest duplicate d1 promoted, got %s", promoted.EventID)
				}
				if promoted.DuplicateID != "" {
					t.Errorf("promoted event should have DuplicateID cleared, got %q", promoted.DuplicateID)
				}
				if len(promoted.RepeatedAt) != 2 {
					t.Fatalf("expected 2 repeats, got %d", len(promoted.RepeatedAt))
				}
				if promoted.RepeatedAt[0] != "2024-01-01T03:00:00Z" {
					t.Errorf("repeat[0] = %s, want 2024-01-01T03:00:00Z", promoted.RepeatedAt[0])
				}
				if promoted.RepeatedAt[1] != "2024-01-01T05:00:00Z" {
					t.Errorf("repeat[1] = %s, want 2024-01-01T05:00:00Z", promoted.RepeatedAt[1])
				}
			},
		},
		{
			name: "single orphaned duplicate promoted as-is",
			events: []models.SCTEvent{
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "missing-orig", EventType: "X"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				if result[0].DuplicateID != "" {
					t.Errorf("promoted event should have DuplicateID cleared, got %q", result[0].DuplicateID)
				}
				if len(result[0].RepeatedAt) != 0 {
					t.Errorf("single orphan should have no repeats, got %d", len(result[0].RepeatedAt))
				}
			},
		},
		{
			name: "mix of originals, duplicates, and orphans",
			events: []models.SCTEvent{
				{EventID: "orig1", Ts: "2024-01-01T00:00:00Z"},
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "orig1"},
				{EventID: "orphan2", Ts: "2024-01-01T04:00:00Z", DuplicateID: "gone"},
				{EventID: "orphan1", Ts: "2024-01-01T02:00:00Z", DuplicateID: "gone"},
				{EventID: "orig2", Ts: "2024-01-01T05:00:00Z"},
			},
			wantCount: 3, // orig1 (with d1 repeat), orig2, promoted orphan1
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				// orig1 should have 1 repeat
				if result[0].EventID != "orig1" {
					t.Fatalf("result[0] expected orig1, got %s", result[0].EventID)
				}
				if len(result[0].RepeatedAt) != 1 {
					t.Fatalf("orig1 expected 1 repeat, got %d", len(result[0].RepeatedAt))
				}
				// orig2 should have no repeats
				if result[1].EventID != "orig2" {
					t.Fatalf("result[1] expected orig2, got %s", result[1].EventID)
				}
				if len(result[1].RepeatedAt) != 0 {
					t.Errorf("orig2 expected 0 repeats, got %d", len(result[1].RepeatedAt))
				}
				// promoted orphan
				promoted := result[2]
				if promoted.EventID != "orphan1" {
					t.Fatalf("result[2] expected orphan1 (earliest), got %s", promoted.EventID)
				}
				if promoted.DuplicateID != "" {
					t.Errorf("promoted orphan should have DuplicateID cleared")
				}
				if len(promoted.RepeatedAt) != 1 {
					t.Fatalf("promoted orphan expected 1 repeat, got %d", len(promoted.RepeatedAt))
				}
			},
		},
		{
			name: "all events are duplicates of same missing original",
			events: []models.SCTEvent{
				{EventID: "d3", Ts: "2024-01-01T03:00:00Z", DuplicateID: "gone"},
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "gone"},
				{EventID: "d2", Ts: "2024-01-01T02:00:00Z", DuplicateID: "gone"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				if result[0].EventID != "d1" {
					t.Errorf("expected earliest d1 promoted, got %s", result[0].EventID)
				}
				if len(result[0].RepeatedAt) != 2 {
					t.Errorf("expected 2 repeats, got %d", len(result[0].RepeatedAt))
				}
			},
		},
		{
			name: "original keeps its own summary",
			events: []models.SCTEvent{
				{EventID: "orig", Ts: "2024-01-01T00:00:00Z", Summary: "original summary"},
				{EventID: "dup", Ts: "2024-01-01T01:00:00Z", DuplicateID: "orig", Summary: "duplicate summary"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				if result[0].Summary != "original summary" {
					t.Errorf("expected original summary, got %q", result[0].Summary)
				}
			},
		},
		{
			name: "promoted orphan keeps its own summary",
			events: []models.SCTEvent{
				{EventID: "d2", Ts: "2024-01-01T02:00:00Z", DuplicateID: "gone", Summary: "second"},
				{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "gone", Summary: "first"},
			},
			wantCount: 1,
			wantChecks: func(t *testing.T, result []models.SCTEvent) {
				if result[0].Summary != "first" {
					t.Errorf("expected summary of earliest orphan, got %q", result[0].Summary)
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := deduplicateEvents(tt.events)
			if len(result) != tt.wantCount {
				t.Fatalf("got %d events, want %d", len(result), tt.wantCount)
			}
			if tt.wantChecks != nil {
				tt.wantChecks(t, result)
			}
		})
	}
}

func TestPromotedDuplicateShowsMessage(t *testing.T) {
	events := deduplicateEvents([]models.SCTEvent{
		{EventID: "d2", Ts: "2024-01-01T02:00:00Z", DuplicateID: "gone", Message: "second message"},
		{EventID: "d1", Ts: "2024-01-01T01:00:00Z", DuplicateID: "gone", Message: "first message"},
	})

	raw, err := json.Marshal(models.SCTEventsResponse{RunID: "run-1", Events: events})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var got []map[string]any
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("got %d events, want 1", len(got))
	}
	if got[0]["message"] != "first message" {
		t.Errorf("message = %v, want %q", got[0]["message"], "first message")
	}
	if _, ok := got[0]["summarized"]; ok {
		t.Errorf("promoted duplicate is marked summarized: %v", got[0]["summarized"])
	}
}

// stubEventsAPI serves one summarized ERROR event and one CRITICAL event with
// no summary for stubRunID, and returns a client bound to it.
func stubEventsAPI(t *testing.T) *api.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload string
		switch r.URL.Path {
		case "/api/v1/client/sct/" + stubRunID + "/events/CRITICAL/get":
			payload = `[{"event_id": "c1", "severity": "CRITICAL", "ts": "2026-10-01T10:05:00Z",
				"message": "critical full text", "summary": null}]`
		case "/api/v1/client/sct/" + stubRunID + "/events/ERROR/get":
			payload = `[{"event_id": "e1", "severity": "ERROR", "ts": "2026-10-01T10:00:00Z",
				"message": "error full text", "summary": "error short text"}]`
		default:
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status": "ok", "response": ` + payload + `}`))
	}))
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	return client
}

// runEvents executes `run events` for stubRunID and returns its JSON output
// keyed by event ID.
func runEvents(t *testing.T, raw bool) map[string]map[string]any {
	t.Helper()
	var buf bytes.Buffer
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	ctx = contextWithAPIClient(ctx, stubEventsAPI(t))
	ctx = contextWithOutputter(ctx, output.New(&buf, false))
	runEventsCmd.SetContext(ctx)
	require.NoError(t, runEventsCmd.Flags().Set("run-id", stubRunID))
	require.NoError(t, runEventsCmd.Flags().Set("raw", strconv.FormatBool(raw)))
	t.Cleanup(func() {
		_ = runEventsCmd.Flags().Set("run-id", "")
		_ = runEventsCmd.Flags().Set("raw", "false")
	})

	require.NoError(t, runEventsCmd.RunE(runEventsCmd, nil))
	var events []map[string]any
	require.NoError(t, json.Unmarshal(buf.Bytes(), &events))
	byID := make(map[string]map[string]any, len(events))
	for _, e := range events {
		byID[e["event_id"].(string)] = e
	}
	require.Len(t, byID, 2)
	return byID
}

func TestRunEventsCmd_ShowsSummaryByDefault(t *testing.T) {
	got := runEvents(t, false)

	assert.Equal(t, "error short text", got["e1"]["message"])
	assert.Equal(t, true, got["e1"]["summarized"])
	assert.NotContains(t, got["e1"], "summary")

	assert.Equal(t, "critical full text", got["c1"]["message"])
	assert.NotContains(t, got["c1"], "summarized")
}

func TestRunEventsCmd_RawShowsOriginalMessage(t *testing.T) {
	got := runEvents(t, true)

	assert.Equal(t, "error full text", got["e1"]["message"])
	assert.NotContains(t, got["e1"], "summarized")
	assert.NotContains(t, got["e1"], "summary")

	assert.Equal(t, "critical full text", got["c1"]["message"])
}
