package cmd

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestEventListView_Headers(t *testing.T) {
	t.Parallel()
	v := &EventListView{}
	assert.Equal(t, []string{"Severity", "EventType", "Timestamp", "Node", "Message"}, v.Headers())
}

func TestEventListView_Rows(t *testing.T) {
	t.Parallel()
	v := &EventListView{
		Events: []EventView{
			{
				Severity:  "ERROR",
				EventType: "DatabaseError",
				Message:   "connection refused",
				Timestamp: "2026-03-23 01:19:14 UTC",
				Node:      "node-1",
			},
			{
				Severity:  "CRITICAL",
				EventType: "CassandraStressLogEvent",
				Message:   "fatal error",
				Timestamp: "2026-03-23 01:20:00 UTC",
				Node:      "",
			},
		},
	}

	rows := v.Rows()
	assert.Len(t, rows, 2)
	assert.Equal(t, "ERROR", rows[0][0])
	assert.Equal(t, "DatabaseError", rows[0][1])
	assert.Equal(t, "2026-03-23 01:19:14 UTC", rows[0][2])
	assert.Equal(t, "node-1", rows[0][3])
	assert.Equal(t, "connection refused", rows[0][4])
}

func TestEventListView_Rows_TruncatesLongMessage(t *testing.T) {
	t.Parallel()
	longMsg := ""
	for i := 0; i < 150; i++ {
		longMsg += "x"
	}
	v := &EventListView{
		Events: []EventView{
			{Severity: "ERROR", Message: longMsg},
		},
	}

	rows := v.Rows()
	assert.Len(t, rows[0][4], 123) // 120 + "..."
	assert.True(t, rows[0][4][120:] == "...")
}

func TestEventListView_Rows_Empty(t *testing.T) {
	t.Parallel()
	v := &EventListView{Events: []EventView{}}
	assert.Empty(t, v.Rows())
}
