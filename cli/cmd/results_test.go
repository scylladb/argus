package cmd

import (
	"net/url"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestReleaseResultsRoute(t *testing.T) {
	route := releaseResultsRoute("scylla 2026.1", "throughput", []string{"PASS", "ERROR"},
		map[string]string{"since": "2026-10-01", "sutUntil": "2026-10-20"})

	path, query, found := strings.Cut(route, "?")
	require.True(t, found)
	assert.Equal(t, "/api/v1/results/release/scylla%202026.1", path)

	params, err := url.ParseQuery(query)
	require.NoError(t, err)
	assert.Equal(t, "throughput", params.Get("table"))
	assert.Equal(t, []string{"PASS", "ERROR"}, params["status[]"])
	assert.Equal(t, "2026-10-01", params.Get("since"))
	assert.Equal(t, "2026-10-20", params.Get("sutUntil"))
	assert.False(t, params.Has("until"))
}

func TestReleaseResultsWindowFlags(t *testing.T) {
	for flag := range releaseResultsWindowParams {
		f := genericResultsQueryCmd.Flags().Lookup(flag)
		require.NotNil(t, f, "query command is missing the --%s flag", flag)
		assert.NotEmpty(t, f.Usage)
	}
	table := genericResultsQueryCmd.Flags().Lookup("table")
	require.NotNil(t, table)
	assert.Equal(t, []string{"true"}, table.Annotations["cobra_annotation_bash_completion_one_required_flag"])
}
