package cmd

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNemesisListView_Headers(t *testing.T) {
	t.Parallel()
	v := &NemesisListView{}
	assert.Equal(t, []string{"Name", "Status", "TargetNode", "StartTime", "EndTime", "Duration"}, v.Headers())
}

func TestNemesisListView_Rows(t *testing.T) {
	t.Parallel()
	v := &NemesisListView{
		Nemeses: []NemesisView{
			{
				Name:       "DisruptKillScylla",
				Status:     "succeeded",
				TargetNode: "node-1",
				StartTime:  "2026-03-23 01:00:00 UTC",
				EndTime:    "2026-03-23 01:05:00 UTC",
				Duration:   "5m0s",
			},
			{
				Name:       "DisruptDecommission",
				Status:     "failed",
				TargetNode: "node-2",
				StartTime:  "2026-03-23 02:00:00 UTC",
				EndTime:    "2026-03-23 02:01:00 UTC",
				Duration:   "1m0s",
				StackTrace: "panic: something",
			},
		},
	}

	rows := v.Rows()
	assert.Len(t, rows, 2)
	assert.Equal(t, []string{"DisruptKillScylla", "succeeded", "node-1", "2026-03-23 01:00:00 UTC", "2026-03-23 01:05:00 UTC", "5m0s"}, rows[0])
	assert.Equal(t, "failed", rows[1][1])
}

func TestNemesisListView_Rows_Empty(t *testing.T) {
	t.Parallel()
	v := &NemesisListView{Nemeses: []NemesisView{}}
	assert.Empty(t, v.Rows())
}
