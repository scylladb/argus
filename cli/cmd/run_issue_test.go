package cmd

import "testing"

func TestIssueSubmitRoute(t *testing.T) {
	tests := []struct {
		name    string
		eventID string
		want    string
	}{
		{name: "run link", eventID: "", want: "/api/v1/test/t1/run/r1/issues/submit"},
		{name: "event link", eventID: "e1", want: "/api/v1/test/t1/run/r1/issues/event/e1/submit"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := issueSubmitRoute("t1", "r1", tt.eventID); got != tt.want {
				t.Errorf("issueSubmitRoute() = %q, want %q", got, tt.want)
			}
		})
	}
}
