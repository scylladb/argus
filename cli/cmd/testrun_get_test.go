package cmd

import (
	"bytes"
	"context"
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

const stubRunID = "5e7b3f0c-1d2a-4c8e-9f6b-0a1b2c3d4e5f"

const stubSCTRun = `{
	"id": "` + stubRunID + `", "build_id": "scylla-master/longevity/longevity-10gb-3h-test", "build_number": 412,
	"status": "failed", "investigation_status": "not_investigated", "test_name": "longevity_test",
	"packages": [{"name": "scylla-server", "version": "2026.2.0~dev", "date": "20261001", "revision_id": "abc123", "build_id": ""}],
	"logs": [["db-cluster-5e7b3f0c.tar.zst", "https://bucket.s3.amazonaws.com/5e7b3f0c/db-cluster-5e7b3f0c.tar.zst"],
	         ["sct-runner-events-5e7b3f0c.tar.zst", "https://bucket.s3.amazonaws.com/5e7b3f0c/sct-runner-events-5e7b3f0c.tar.zst"]]
}`

// stubRunAPI serves stubSCTRun as an SCT run and returns a client bound to it.
func stubRunAPI(t *testing.T) *api.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload string
		switch r.URL.Path {
		case "/api/v1/run/" + stubRunID + "/type":
			payload = `{"run_type": "scylla-cluster-tests"}`
		case "/api/v1/run/scylla-cluster-tests/" + stubRunID:
			payload = stubSCTRun
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

// runGetRun executes `run get` for stubRunID and returns its JSON output.
func runGetRun(t *testing.T, full bool) string {
	t.Helper()
	var buf bytes.Buffer
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	ctx = contextWithAPIClient(ctx, stubRunAPI(t))
	ctx = contextWithOutputter(ctx, output.New(&buf, false))
	getRunCmd.SetContext(ctx)
	require.NoError(t, getRunCmd.Flags().Set("run-id", stubRunID))
	require.NoError(t, getRunCmd.Flags().Set("full", strconv.FormatBool(full)))
	t.Cleanup(func() {
		_ = getRunCmd.Flags().Set("run-id", "")
		_ = getRunCmd.Flags().Set("full", "false")
	})

	require.NoError(t, getRunCmd.RunE(getRunCmd, nil))
	return buf.String()
}

func TestGetRunCmd_FullPrintsTheWholeRun(t *testing.T) {
	out := runGetRun(t, true)

	assert.Contains(t, out, `"packages"`)
	assert.Contains(t, out, `"scylla-server"`)
	assert.Contains(t, out, `"logs"`)
}

func TestGetRunCmd_SummaryLeavesOutTheWholeRunFields(t *testing.T) {
	out := runGetRun(t, false)

	assert.Contains(t, out, stubRunID)
	assert.NotContains(t, out, `"packages"`)
	assert.NotContains(t, out, `"logs"`)
}

func TestRunCmd_HasNoDetailsSubcommand(t *testing.T) {
	for _, c := range runCmd.Commands() {
		assert.NotEqual(t, "details", c.Name())
	}
}
