package cmd

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

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

func TestIssueRunsCmd(t *testing.T) {
	assert.Contains(t, issueCmd.Commands(), issueRunsCmd)

	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{}))
	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{"SCT-1", "SCT-2"}))
	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{""}))
	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{"  "}))
	assert.NoError(t, issueRunsCmd.Args(issueRunsCmd, []string{"SCT-1234"}))

	raw := issueRunsCmd.Flags().Lookup("raw")
	require.NotNil(t, raw, "issue runs is missing the --raw flag")
	assert.Equal(t, "false", raw.DefValue)
	assert.NotEmpty(t, raw.Usage)
}
