package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestReleaseResultsRoute(t *testing.T) {
	route, err := releaseResultsRoute("scylla 2026.1", releaseResultsQuery{
		Table:      "throughput",
		Statuses:   []string{"PASS", "ERROR"},
		Window:     map[string]string{"since": "2026-10-01", "sutUntil": "2026-10-20"},
		Columns:    []string{"ops", "p99"},
		ShowHidden: true,
		RunLimit:   20,
	})
	require.NoError(t, err)

	path, query, found := strings.Cut(route, "?")
	require.True(t, found)
	assert.Equal(t, "/api/v1/results/release/scylla%202026.1", path)

	params, err := url.ParseQuery(query)
	require.NoError(t, err)
	assert.Equal(t, "throughput", params.Get("table"))
	assert.Equal(t, []string{"PASS", "ERROR"}, params["status[]"])
	assert.Equal(t, "2026-10-01", params.Get("since"))
	assert.Equal(t, "2026-10-20", params.Get("sutUntil"))
	assert.Equal(t, "true", params.Get("includeHidden"))
	assert.Equal(t, []string{"ops", "p99"}, params["columns[]"])
	assert.Equal(t, "20", params.Get("runLimit"))
	assert.False(t, params.Has("tableLimit"))
	assert.False(t, params.Has("until"))
}

func TestReleasePathSegmentRejectsDotSegments(t *testing.T) {
	for _, release := range []string{".", "..", "...", ""} {
		_, err := releasePathSegment(release)
		assert.Error(t, err, "release %q", release)
	}
	segment, err := releasePathSegment("a/../b")
	require.NoError(t, err)
	assert.Equal(t, "a%2F..%2Fb", segment)
}

func TestReleaseResultsWindowFlags(t *testing.T) {
	for flag := range releaseResultsWindowParams {
		f := genericResultsQueryCmd.Flags().Lookup(flag)
		require.NotNil(t, f, "query command is missing the --%s flag", flag)
		assert.NotEmpty(t, f.Usage)
	}
	table := genericResultsQueryCmd.Flags().Lookup("table")
	require.NotNil(t, table)
	assert.Equal(t, []string{"true"}, table.Annotations[cobra.BashCompOneRequiredFlag])
}

// runResultsCommand executes cmd with args and flags against a stub API that
// answers every request with payload. It returns the JSON output and the URLs
// the stub received.
func runResultsCommand(t *testing.T, cmd *cobra.Command, args []string, payload string,
	flags map[string]string,
) (string, []*url.URL, error) {
	t.Helper()
	var received []*url.URL
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received = append(received, r.URL)
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
	cmd.SetContext(ctx)
	for name, value := range flags {
		require.NoError(t, cmd.Flags().Set(name, value))
	}
	t.Cleanup(func() { resetFlags(cmd) })

	err = cmd.RunE(cmd, args)
	return buf.String(), received, err
}

const releaseResultsPayload = `[{"table": "throughput", "description": "", "tests": [
	{"test_id": "t1", "test_name": "longevity", "build_id": "scylla-master/longevity", "runs_truncated": true,
	 "runs": [{"run_id": "r1", "build_number": 7, "scylla_version": "2026.2.0",
	           "started_at": "2026-10-20T08:12:00.000Z", "sut_timestamp": null,
	           "cells": [{"row": "write", "column": "ops", "value": 1200.5, "status": "PASS"}]}]}]}]`

func TestGenericResultsQueryCmd_SendsTheFlagsAndDecodesTheGroups(t *testing.T) {
	out, received, err := runResultsCommand(t, genericResultsQueryCmd, []string{"scylla-master"},
		releaseResultsPayload, map[string]string{"table": "throughput", "status": "ERROR", "until": "2026-10-21"})
	require.NoError(t, err)

	require.Len(t, received, 1)
	assert.Equal(t, "/api/v1/results/release/scylla-master", received[0].Path)
	assert.Equal(t, "throughput", received[0].Query().Get("table"))
	assert.Equal(t, []string{"ERROR"}, received[0].Query()["status[]"])
	assert.Equal(t, "2026-10-21", received[0].Query().Get("until"))

	var groups models.ResultGroups
	require.NoError(t, json.Unmarshal([]byte(out), &groups))
	require.Len(t, groups, 1)
	require.Len(t, groups[0].Tests, 1)
	assert.True(t, groups[0].Tests[0].RunsTruncated)
	assert.Equal(t, 7, *groups[0].Tests[0].Runs[0].BuildNumber)
	assert.Equal(t, 1200.5, groups[0].Tests[0].Runs[0].Cells[0].Value)
}

func TestGenericResultsQueryCmd_RejectsADotRelease(t *testing.T) {
	_, received, err := runResultsCommand(t, genericResultsQueryCmd, []string{".."}, "[]",
		map[string]string{"table": "throughput"})

	require.Error(t, err)
	assert.Empty(t, received)
}

func TestGenericResultsQueryCmd_RejectsAnEmptyTable(t *testing.T) {
	_, received, err := runResultsCommand(t, genericResultsQueryCmd, []string{"scylla-master"}, "[]",
		map[string]string{"table": " "})

	require.Error(t, err)
	assert.Empty(t, received)
}

func TestGenericResultsTablesCmd_ListsTheTables(t *testing.T) {
	out, received, err := runResultsCommand(t, genericResultsTablesCmd, []string{"scylla-master"},
		`[{"name": "latency", "description": "", "columns": ["p99"], "tests": 3}]`,
		map[string]string{"show-hidden": "true"})
	require.NoError(t, err)

	require.Len(t, received, 1)
	assert.Equal(t, "/api/v1/results/release/scylla-master/tables", received[0].Path)
	assert.Equal(t, "true", received[0].Query().Get("includeHidden"))

	var tables models.ResultTableSummaries
	require.NoError(t, json.Unmarshal([]byte(out), &tables))
	assert.Equal(t, models.ResultTableSummaries{{Name: "latency", Columns: []string{"p99"}, Tests: 3}}, tables)
}

func TestGenericResultsQueryCmd_SendsTheColumnsAndLimits(t *testing.T) {
	_, received, err := runResultsCommand(t, genericResultsQueryCmd, []string{"scylla-master"}, "[]",
		map[string]string{"table": "throughput", "column": "ops", "run-limit": "5", "table-limit": "50"})
	require.NoError(t, err)

	require.Len(t, received, 1)
	assert.Equal(t, []string{"ops"}, received[0].Query()["columns[]"])
	assert.Equal(t, "5", received[0].Query().Get("runLimit"))
	assert.Equal(t, "50", received[0].Query().Get("tableLimit"))
}

func TestGenericResultsQueryCmd_RejectsANegativeLimit(t *testing.T) {
	_, received, err := runResultsCommand(t, genericResultsQueryCmd, []string{"scylla-master"}, "[]",
		map[string]string{"table": "throughput", "run-limit": "-1"})

	require.Error(t, err)
	assert.Empty(t, received)
}
