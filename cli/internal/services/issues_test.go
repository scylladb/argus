package services_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newIssueSvc spins up an httptest server for mux and returns an IssueService
// wired to it.
func newIssueSvc(t *testing.T, mux *http.ServeMux) *services.IssueService {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	return services.NewIssueService(client)
}

func TestIssueService_Links(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/issues/SCT-1234/links", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, json.RawMessage(`{
			"issue": {"key": "SCT-1234", "summary": "Nemesis fails to restart node", "state": "in progress",
				"permalink": "https://scylladb.atlassian.net/browse/SCT-1234", "subtype": "jira"},
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
		}`))
	})

	links, err := newIssueSvc(t, mux).Links(context.Background(), "SCT-1234")

	require.NoError(t, err)
	assert.Contains(t, string(links.Raw()), `"key":"SCT-1234"`)
	assert.Contains(t, string(links.Raw()), `"plugin_name":"generic"`)
	require.Len(t, links.Links, 2)
	assert.Equal(t, "run-2", links.Links[0].RunID)
	assert.Equal(t, "longevity-100gb-4h", links.Links[0].TestName)
	require.NotNil(t, links.Links[0].BuildNumber)
	assert.Equal(t, 412, *links.Links[0].BuildNumber)
	assert.Equal(t, "https://argus/test/rel/g/longevity-100gb-4h/412", links.Links[0].URL)
	assert.Equal(t, "run-1", links.Links[1].RunID)
	assert.Equal(t, "2026.2.0", links.Summaries()[1].Version)
}

func TestIssueService_Links_UnknownKey(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/issues/SCT-999999/links", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, json.RawMessage(`{"issue": null, "links": []}`))
	})

	links, err := newIssueSvc(t, mux).Links(context.Background(), "SCT-999999")

	require.NoError(t, err)
	assert.JSONEq(t, `{"issue": null, "links": []}`, string(links.Raw()))
	raw, err := json.Marshal(links.Summaries())
	require.NoError(t, err)
	assert.JSONEq(t, `[]`, string(raw))
}

func TestIssueService_Links_RejectedKey(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/issues/SCT1234/links", func(w http.ResponseWriter, _ *http.Request) {
		jsonErr(t, w, "Not an issue key: 'SCT1234'. Expected a Jira key such as SCT-1234.")
	})

	_, err := newIssueSvc(t, mux).Links(context.Background(), "SCT1234")

	require.Error(t, err)
	assert.Contains(t, err.Error(), "Not an issue key: 'SCT1234'")
}
