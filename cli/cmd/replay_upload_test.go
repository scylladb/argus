package cmd

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// earlyAnswer answers every request without reading its body, like a server
// that rejects an upload early.
type earlyAnswer struct {
	status      int
	contentType string
	body        string
}

func (e earlyAnswer) RoundTrip(req *http.Request) (*http.Response, error) {
	_ = req.Body.Close()
	contentType := e.contentType
	if contentType == "" {
		contentType = "text/plain"
	}
	return &http.Response{
		StatusCode: e.status,
		Header:     http.Header{"Content-Type": []string{contentType}},
		Body:       io.NopCloser(strings.NewReader(e.body)),
		Request:    req,
	}, nil
}

// An upload the server answers before it reads the body reports the server's
// answer, not the closed pipe it leaves behind.
func TestUploadReplay_EarlyAnswerReportsServerError(t *testing.T) {
	t.Parallel()
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	client, err := api.New("https://argus.example.com",
		api.WithHTTPClient(&http.Client{Transport: earlyAnswer{status: http.StatusRequestEntityTooLarge}}))
	require.NoError(t, err)

	_, err = uploadReplay(context.Background(), client, []string{file}, replayOptions{BackfillLogs: true}, zerolog.Nop())
	require.Error(t, err)
	assert.ErrorContains(t, err, "413")
	assert.NotErrorIs(t, err, io.ErrClosedPipe)
}

// A success answer to an upload the server did not read in full is an error.
func TestUploadReplay_EarlySuccessIsAnError(t *testing.T) {
	t.Parallel()
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	client, err := api.New("https://argus.example.com",
		api.WithHTTPClient(&http.Client{Transport: earlyAnswer{
			status:      http.StatusOK,
			contentType: "application/json",
			body:        `{"status":"ok","response":{"total":1,"succeeded":1}}`,
		}}))
	require.NoError(t, err)

	_, err = uploadReplay(context.Background(), client, []string{file}, replayOptions{BackfillLogs: true}, zerolog.Nop())
	require.ErrorIs(t, err, io.ErrClosedPipe)
	assert.ErrorContains(t, err, "whole archive")
}

// The text report prints the full Argus link of every replayed run.
func TestRenderReplaySummary_PrintsRunLinks(t *testing.T) {
	t.Parallel()
	var buf strings.Builder
	cmd := &cobra.Command{}
	cmd.SetOut(&buf)
	cmd.SetContext(context.Background())

	report := replayReport{
		ReplayIngestSummary: &models.ReplayIngestSummary{Total: 2, Succeeded: 2},
		Runs: runLinks("https://argus.example.com/", []models.ReplayRun{
			{Type: "scylla-cluster-tests", ID: "550e8400-e29b-41d4-a716-446655440000"},
		}, false),
	}
	require.NoError(t, renderReplaySummary(cmd, "text", report))

	assert.Contains(t, buf.String(),
		"Run 550e8400-e29b-41d4-a716-446655440000: "+
			"https://argus.example.com/tests/scylla-cluster-tests/550e8400-e29b-41d4-a716-446655440000\n")
}

// recordingServer reads the whole upload, keeps the request URL and answers
// with a fixed summary.
type recordingServer struct {
	url  chan string
	body string
}

func (r recordingServer) RoundTrip(req *http.Request) (*http.Response, error) {
	_, _ = io.Copy(io.Discard, req.Body)
	_ = req.Body.Close()
	r.url <- req.URL.String()
	return &http.Response{
		StatusCode: http.StatusOK,
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(strings.NewReader(r.body)),
		Request:    req,
	}, nil
}

// A set --as-me reaches the server, and the summary carries the runs.
func TestUploadReplay_SendsAsMe(t *testing.T) {
	t.Parallel()
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	server := recordingServer{
		url: make(chan string, 1),
		body: `{"status":"ok","response":{"total":1,"succeeded":1,` +
			`"runs":[{"type":"scylla-cluster-tests","id":"run-1"}]}}`,
	}
	client, err := api.New("https://argus.example.com", api.WithHTTPClient(&http.Client{Transport: server}))
	require.NoError(t, err)

	asMe := false
	opts := replayOptions{
		BackfillLogs: true,
		AsMe:         &asMe,
		KeepRun:      true,
	}
	summary, err := uploadReplay(context.Background(), client, []string{file}, opts, zerolog.Nop())
	require.NoError(t, err)

	sent, err := url.Parse(<-server.url)
	require.NoError(t, err)
	assert.Equal(t, "false", sent.Query().Get("as_me"))
	assert.False(t, sent.Query().Has("create_missing_tests"), "an unset flag leaves the default to the server")
	assert.False(t, sent.Query().Has("local_runs"), "--keep-run turns the local-runs default off")
	assert.Equal(t, []models.ReplayRun{{Type: "scylla-cluster-tests", ID: "run-1"}}, summary.Runs)
}

// A new local run shows its build next to its run ID.
func TestRenderReplaySummary_PrintsTheBuild(t *testing.T) {
	t.Parallel()
	three := 3
	var buf strings.Builder
	cmd := &cobra.Command{}
	cmd.SetOut(&buf)
	cmd.SetContext(context.Background())

	report := replayReport{
		ReplayIngestSummary: &models.ReplayIngestSummary{Total: 1, Succeeded: 1},
		Runs: runLinks("https://argus.example.com", []models.ReplayRun{
			{Type: "scylla-cluster-tests", ID: "run-1", BuildID: "rel/jdoe/job", BuildNumber: &three},
		}, false),
	}
	require.NoError(t, renderReplaySummary(cmd, "text", report))

	assert.Contains(t, buf.String(),
		"Run run-1 (rel/jdoe/job#3): https://argus.example.com/tests/scylla-cluster-tests/run-1\n")
}

// A dry run names the build each run would become, links nothing, and keeps
// the runs in the JSON report.
func TestRenderReplaySummary_DryRunNamesTheBuild(t *testing.T) {
	t.Parallel()
	four := 4
	runs := []models.ReplayRun{
		{Type: "scylla-cluster-tests", ID: "run-1", BuildID: "rel/jdoe/job", BuildNumber: &four},
	}
	report := replayReport{
		ReplayIngestSummary: &models.ReplayIngestSummary{Total: 1, Succeeded: 1, Runs: runs},
		Runs:                runLinks("https://argus.example.com", runs, true),
	}

	var text strings.Builder
	cmd := &cobra.Command{}
	cmd.SetOut(&text)
	cmd.SetContext(context.Background())
	require.NoError(t, renderReplaySummary(cmd, "text", report))
	assert.Contains(t, text.String(), "Run run-1 would replay as (rel/jdoe/job#4)\n")
	assert.NotContains(t, text.String(), "https://")

	encoded, err := json.Marshal(report)
	require.NoError(t, err)
	assert.JSONEq(t, `[{"type":"scylla-cluster-tests","id":"run-1",`+
		`"build_id":"rel/jdoe/job","build_number":4,"failed":false}]`,
		string(reportRuns(t, encoded)))
}

// A run whose submit_run failed gets no link: the run may not exist.
func TestRenderReplaySummary_FailedRunGetsNoLink(t *testing.T) {
	t.Parallel()
	one := 1
	runs := []models.ReplayRun{
		{Type: "scylla-cluster-tests", ID: "run-1", BuildID: "local-runs/jdoe/job", BuildNumber: &one, Failed: true},
	}
	report := replayReport{
		ReplayIngestSummary: &models.ReplayIngestSummary{Total: 1, Failed: 1, Runs: runs},
		Runs:                runLinks("https://argus.example.com", runs, false),
	}

	var text strings.Builder
	cmd := &cobra.Command{}
	cmd.SetOut(&text)
	cmd.SetContext(context.Background())
	require.NoError(t, renderReplaySummary(cmd, "text", report))
	assert.Contains(t, text.String(),
		"Run run-1 (local-runs/jdoe/job#1) failed: see the errors below\n")
	assert.NotContains(t, text.String(), "https://")

	encoded, err := json.Marshal(report)
	require.NoError(t, err)
	assert.JSONEq(t, `[{"type":"scylla-cluster-tests","id":"run-1",`+
		`"build_id":"local-runs/jdoe/job","build_number":1,"failed":true}]`,
		string(reportRuns(t, encoded)))
}

func reportRuns(t *testing.T, encoded []byte) json.RawMessage {
	t.Helper()
	var doc struct {
		Runs json.RawMessage `json:"runs"`
	}
	require.NoError(t, json.Unmarshal(encoded, &doc))
	return doc.Runs
}

// Without --keep-run the CLI asks the server for the local-runs default.
func TestUploadReplay_AsksForLocalRunsByDefault(t *testing.T) {
	t.Parallel()
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	server := recordingServer{url: make(chan string, 1), body: `{"status":"ok","response":{"total":1}}`}
	client, err := api.New("https://argus.example.com", api.WithHTTPClient(&http.Client{Transport: server}))
	require.NoError(t, err)

	_, err = uploadReplay(context.Background(), client, []string{file}, replayOptions{BackfillLogs: true}, zerolog.Nop())
	require.NoError(t, err)

	sent, err := url.Parse(<-server.url)
	require.NoError(t, err)
	assert.Equal(t, "true", sent.Query().Get("local_runs"))
}

// --test reaches the server as test_name.
func TestUploadReplay_SendsTheTestName(t *testing.T) {
	t.Parallel()
	file := filepath.Join(t.TempDir(), "run.jsonl")
	require.NoError(t, os.WriteFile(file, []byte(`{"a":1}`+"\n"), 0o600))

	server := recordingServer{url: make(chan string, 1), body: `{"status":"ok","response":{"total":1}}`}
	client, err := api.New("https://argus.example.com", api.WithHTTPClient(&http.Client{Transport: server}))
	require.NoError(t, err)

	opts := replayOptions{BackfillLogs: true, TestName: "my-feature"}
	_, err = uploadReplay(context.Background(), client, []string{file}, opts, zerolog.Nop())
	require.NoError(t, err)

	sent, err := url.Parse(<-server.url)
	require.NoError(t, err)
	assert.Equal(t, "my-feature", sent.Query().Get("test_name"))
	assert.Equal(t, "true", sent.Query().Get("local_runs"))
}

func TestCollectFiles_FindsPythonClientNamesByRunID(t *testing.T) {
	dir := t.TempDir()
	want := filepath.Join(dir,
		"argus_replay_log_cc54896b-d95b-4f60-b6d8-42c65b13ca48_1791278702821085000_70948_98b1e2bebc1e4d379c9ed1553f050c47.jsonl")
	other := filepath.Join(dir,
		"argus_replay_log_91c226dc-a057-4ad4-a0b8-bf8bc73031b9_1791281071111486000_16748_a5ef5489ee31459495bec948cb779d06.jsonl")
	for _, p := range []string{want, other} {
		require.NoError(t, os.WriteFile(p, []byte(`{"ts":1}`+"\n"), 0o644))
	}

	all, err := collectFiles(dir, "", nil)
	require.NoError(t, err)
	assert.Equal(t, []string{other, want}, all)

	one, err := collectFiles(dir, "cc54896b-d95b-4f60-b6d8-42c65b13ca48", nil)
	require.NoError(t, err)
	assert.Equal(t, []string{want}, one)
}
