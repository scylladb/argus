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
	"github.com/scylladb/argus/cli/internal/output"
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
	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{"."}))
	assert.Error(t, issueRunsCmd.Args(issueRunsCmd, []string{" .. "}))
	assert.NoError(t, issueRunsCmd.Args(issueRunsCmd, []string{"SCT-1234"}))

	raw := issueRunsCmd.Flags().Lookup("raw")
	require.NotNil(t, raw, "issue runs is missing the --raw flag")
	assert.Equal(t, "false", raw.DefValue)
	assert.NotEmpty(t, raw.Usage)
}

const issueLinksPayload = `{
	"issue": {"key": "SCT-1234", "summary": "Nemesis fails to restart node", "subtype": "jira"},
	"links": [
		{"run_id": "run-2", "test_id": "test-1", "test_name": "longevity-100gb-4h", "plugin_name": "scylla-cluster-tests",
		 "status": "failed", "start_time": "2026-09-30T22:10:44.000Z", "build_id": "rel/g/longevity-100gb-4h",
		 "build_number": 412, "scylla_version": "2026.2.0~dev", "product_version": null,
		 "linked_on": "2026-10-01T07:02:13.540Z", "url": "https://argus/test/rel/g/longevity-100gb-4h/412"},
		{"run_id": "run-1", "test_id": "test-2", "test_name": "artifacts-ubuntu", "plugin_name": "generic",
		 "status": "passed", "start_time": "2026-09-29T08:00:00.000Z", "build_id": "rel/g/artifacts-ubuntu",
		 "build_number": 7, "scylla_version": null, "product_version": "2026.2.0", "linked_on": null,
		 "url": "https://argus/test/rel/g/artifacts-ubuntu/7"}
	]
}`

// runIssueRuns executes `issue runs` with args against a stub API that serves
// issueLinksPayload for SCT-1234 and an empty result for any other key. It
// returns the JSON output and the request paths the stub received.
func runIssueRuns(t *testing.T, raw bool, args ...string) (string, []string) {
	t.Helper()
	var paths []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.URL.EscapedPath())
		payload := `{"issue": null, "links": []}`
		if r.URL.Path == "/api/v1/issues/SCT-1234/links" {
			payload = issueLinksPayload
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status": "ok", "response": ` + payload + `}`))
	}))
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	var buf bytes.Buffer
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	ctx = contextWithAPIClient(ctx, client)
	ctx = contextWithOutputter(ctx, output.New(&buf, false))
	issueRunsCmd.SetContext(ctx)
	require.NoError(t, issueRunsCmd.Flags().Set("raw", strconv.FormatBool(raw)))
	t.Cleanup(func() { _ = issueRunsCmd.Flags().Set("raw", "false") })

	require.NoError(t, issueRunsCmd.RunE(issueRunsCmd, args))
	return buf.String(), paths
}

func TestIssueRunsCmd_PrintsRunRows(t *testing.T) {
	out, paths := runIssueRuns(t, false, "SCT-1234")

	assert.Equal(t, []string{"/api/v1/issues/SCT-1234/links"}, paths)
	assert.JSONEq(t, `[
		{"id": "run-2", "test": "longevity-100gb-4h", "build_id": "rel/g/longevity-100gb-4h", "build_number": 412,
		 "version": "2026.2.0~dev", "status": "failed", "start_time": "2026-09-30T22:10:44.000Z",
		 "argus_url": "https://argus/test/rel/g/longevity-100gb-4h/412"},
		{"id": "run-1", "test": "artifacts-ubuntu", "build_id": "rel/g/artifacts-ubuntu", "build_number": 7,
		 "version": "2026.2.0", "status": "passed", "start_time": "2026-09-29T08:00:00.000Z",
		 "argus_url": "https://argus/test/rel/g/artifacts-ubuntu/7"}
	]`, out)
}

func TestIssueRunsCmd_TrimsTheKey(t *testing.T) {
	_, paths := runIssueRuns(t, false, " SCT-1234 ")

	assert.Equal(t, []string{"/api/v1/issues/SCT-1234/links"}, paths)
}

func TestIssueRunsCmd_UnknownKeyPrintsEmptyList(t *testing.T) {
	out, _ := runIssueRuns(t, false, "SCT-999999")

	assert.JSONEq(t, `[]`, out)
}

func TestIssueRunsCmd_RawPrintsIssueAndLinks(t *testing.T) {
	out, _ := runIssueRuns(t, true, "SCT-1234")

	var got struct {
		Issue map[string]any   `json:"issue"`
		Links []map[string]any `json:"links"`
	}
	require.NoError(t, json.Unmarshal([]byte(out), &got))
	assert.Equal(t, "SCT-1234", got.Issue["key"])
	require.Len(t, got.Links, 2)
	assert.Equal(t, "run-2", got.Links[0]["run_id"])
	assert.Equal(t, "https://argus/test/rel/g/artifacts-ubuntu/7", got.Links[1]["url"])
}
