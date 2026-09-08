package cmd

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestResultsRouteIncludeHidden(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	base := resultsRoute(testID, runID, false)
	assert.NotContains(t, base, "?", "default route must carry no query params")
	assert.Equal(t, "/api/v1/run/"+testID+"/"+runID+"/fetch_results", base)

	assert.Equal(t, base+"?includeHidden=true", resultsRoute(testID, runID, true))
}

func TestResultsCmdHasShowHiddenFlag(t *testing.T) {
	f := resultsCmd.Flags().Lookup("show-hidden")
	require.NotNil(t, f, "results command is missing the --show-hidden flag")
	assert.Equal(t, "false", f.DefValue)
	assert.NotEmpty(t, f.Usage, "--show-hidden is missing help text")
}
