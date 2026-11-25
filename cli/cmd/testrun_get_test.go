package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
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
	resetGetRunFlags(t)
	require.NoError(t, getRunCmd.Flags().Set("run-id", stubRunID))
	require.NoError(t, getRunCmd.Flags().Set("full", strconv.FormatBool(full)))

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

const (
	stubBuildID     = "scylla-master/longevity/longevity-10gb-3h-test"
	stubSecondRunID = "8a1c0d2e-3f4b-4a5c-8d6e-7f8091a2b3c4"
)

// stubBuildAPI serves the build lookup of stubBuildID #412 with the given runs,
// each an SCT run shaped like stubSCTRun.
func stubBuildAPI(t *testing.T, runIDs ...string) (*api.Client, string) {
	t.Helper()
	runs := make([]string, 0, len(runIDs))
	for _, id := range runIDs {
		runs = append(runs, `{"run_id": "`+id+`", "plugin_name": "scylla-cluster-tests"}`)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		payload := ""
		switch {
		case r.URL.Path == "/api/v1/test/"+stubBuildID+"/412":
			payload = `{"runs": [` + strings.Join(runs, ",") + `], "url": "https://argus.example.com/test/` + stubBuildID + `/412"}`
		case strings.HasPrefix(r.URL.Path, "/api/v1/run/scylla-cluster-tests/"):
			payload = strings.ReplaceAll(stubSCTRun, stubRunID, strings.TrimPrefix(r.URL.Path, "/api/v1/run/scylla-cluster-tests/"))
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
	return client, srv.URL
}

// resetGetRunFlags restores the flags of the shared getRunCmd after a test.
func resetGetRunFlags(t *testing.T) {
	t.Helper()
	t.Cleanup(func() {
		for name, value := range map[string]string{"run-id": "", "build-id": "", "build-number": "0", "full": "false"} {
			_ = getRunCmd.Flags().Set(name, value)
			getRunCmd.Flags().Lookup(name).Changed = false
		}
	})
}

// runGetRunByBuild executes `run get` for stubBuildID #412 and returns its JSON output.
func runGetRunByBuild(t *testing.T, client *api.Client) string {
	t.Helper()
	var buf bytes.Buffer
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	ctx = contextWithAPIClient(ctx, client)
	ctx = contextWithOutputter(ctx, output.New(&buf, false))
	getRunCmd.SetContext(ctx)
	resetGetRunFlags(t)
	require.NoError(t, getRunCmd.Flags().Set("build-id", stubBuildID))
	require.NoError(t, getRunCmd.Flags().Set("build-number", "412"))

	require.NoError(t, getRunCmd.RunE(getRunCmd, nil))
	return buf.String()
}

func TestGetRunCmd_SummaryLinksTheRunByItsBuild(t *testing.T) {
	out := runGetRun(t, false)

	assert.Contains(t, out, `"argus_url": "http://127.0.0.1:`)
	assert.Contains(t, out, `/test/`+stubBuildID+`/412"`)
}

func TestGetRunCmd_ByBuildShowsTheRunOfTheBuild(t *testing.T) {
	client, base := stubBuildAPI(t, stubRunID)

	var runs []map[string]any
	require.NoError(t, json.Unmarshal([]byte(runGetRunByBuild(t, client)), &runs))

	require.Len(t, runs, 1)
	assert.Equal(t, stubRunID, runs[0]["id"])
	assert.Equal(t, base+"/test/"+stubBuildID+"/412", runs[0]["argus_url"])
}

func TestGetRunCmd_ByBuildShowsEveryParallelRun(t *testing.T) {
	client, _ := stubBuildAPI(t, stubRunID, stubSecondRunID)

	var runs []map[string]any
	require.NoError(t, json.Unmarshal([]byte(runGetRunByBuild(t, client)), &runs))

	require.Len(t, runs, 2)
	assert.Equal(t, stubRunID, runs[0]["id"])
	assert.Equal(t, stubSecondRunID, runs[1]["id"])
}

func TestGetRunCmd_RejectsRunIDWithBuildID(t *testing.T) {
	resetGetRunFlags(t)
	require.NoError(t, getRunCmd.Flags().Set("run-id", stubRunID))
	require.NoError(t, getRunCmd.Flags().Set("build-id", stubBuildID))
	require.NoError(t, getRunCmd.Flags().Set("build-number", "412"))

	assert.Error(t, getRunCmd.ValidateFlagGroups())
}

func TestGetRunCmd_BuildIDNeedsBuildNumber(t *testing.T) {
	resetGetRunFlags(t)
	require.NoError(t, getRunCmd.Flags().Set("build-id", stubBuildID))

	assert.Error(t, getRunCmd.ValidateFlagGroups())
}

func TestGetRunCmd_NeedsRunIDOrBuildID(t *testing.T) {
	resetGetRunFlags(t)

	assert.Error(t, getRunCmd.ValidateFlagGroups())
}
