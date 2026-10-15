package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newStatusFlagCmd(t *testing.T, args ...string) *cobra.Command {
	t.Helper()
	cmd := &cobra.Command{Use: "status-test"}
	addPytestStatusFlag(cmd)
	require.NoError(t, cmd.ParseFlags(args))
	return cmd
}

func TestPytestStatusFilter_DefaultsToTheDTestFailures(t *testing.T) {
	t.Parallel()
	got, err := pytestStatusFilter(newStatusFlagCmd(t))
	require.NoError(t, err)
	assert.Equal(t, services.DefaultPytestStatuses(), got)
}

func TestPytestStatusFilter_GivenValuesReplaceTheDefault(t *testing.T) {
	t.Parallel()
	got, err := pytestStatusFilter(newStatusFlagCmd(t, "--status", "passed,xpass", "--status", "failure & error"))
	require.NoError(t, err)
	assert.Equal(t, []string{"passed", "xpass", "failure & error"}, got)
}

func TestPytestStatusFilter_EmptyValueLiftsTheFilter(t *testing.T) {
	t.Parallel()
	got, err := pytestStatusFilter(newStatusFlagCmd(t, "--status", ""))
	require.NoError(t, err)
	assert.Empty(t, got)
}

func TestPytestStatusFilter_RejectsUnknownValues(t *testing.T) {
	t.Parallel()
	_, err := pytestStatusFilter(newStatusFlagCmd(t, "--status", "failed"))
	require.Error(t, err)
	assert.Contains(t, err.Error(), `unknown status "failed"`)
}

// runPytestCommand executes cmd with flags against a stub API that answers
// every request with payload. It returns the JSON output and the URLs the
// stub received.
func runPytestCommand(t *testing.T, cmd *cobra.Command, payload string, flags map[string]string) (string, []*url.URL) {
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

	require.NoError(t, cmd.RunE(cmd, nil))
	return buf.String(), received
}

// resetFlags restores every flag of cmd to its default and marks it unset.
func resetFlags(cmd *cobra.Command) {
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		if slice, ok := f.Value.(pflag.SliceValue); ok {
			_ = slice.Replace(nil)
		} else {
			_ = f.Value.Set(f.DefValue)
		}
		f.Changed = false
	})
}

const pytestFilterPayload = `{"total": 0, "hits": [], "barChart": {}, "pieChart": {}}`

func TestPytestResultsCmd_SendsTheDefaultStatuses(t *testing.T) {
	_, received := runPytestCommand(t, pytestResultsCmd, pytestFilterPayload, nil)

	require.Len(t, received, 1)
	assert.Equal(t, services.DefaultPytestStatuses(), received[0].Query()["status[]"])
}

func TestPytestResultsCmd_EmptyStatusSendsNoStatusFilter(t *testing.T) {
	_, received := runPytestCommand(t, pytestResultsCmd, pytestFilterPayload, map[string]string{"status": ""})

	require.Len(t, received, 1)
	assert.False(t, received[0].Query().Has("status[]"))
}

const runPytestResultsPayload = `[
	{"name": "test_a.py::test_pass", "status": "passed"},
	{"name": "test_a.py::test_fail", "status": "failure"},
	{"name": "test_b.py::test_skip", "status": "skipped"},
	{"name": "test_b.py::test_setup", "status": "error"}
]`

func resultNames(t *testing.T, out string) []string {
	t.Helper()
	var rows []struct {
		Name string `json:"name"`
	}
	require.NoError(t, json.Unmarshal([]byte(out), &rows))
	names := make([]string, 0, len(rows))
	for _, r := range rows {
		names = append(names, r.Name)
	}
	return names
}

func TestRunPytestResultsCmd_DefaultKeepsTheFailures(t *testing.T) {
	out, _ := runPytestCommand(t, runPytestResultsCmd, runPytestResultsPayload, map[string]string{"run-id": stubRunID})

	assert.Equal(t, []string{"test_a.py::test_fail", "test_b.py::test_setup"}, resultNames(t, out))
}

func TestRunPytestResultsCmd_EmptyStatusKeepsEveryResult(t *testing.T) {
	out, _ := runPytestCommand(t, runPytestResultsCmd, runPytestResultsPayload,
		map[string]string{"run-id": stubRunID, "status": ""})

	assert.Len(t, resultNames(t, out), 4)
}
