package cmd

import (
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
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
