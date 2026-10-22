package services_test

import (
	"testing"

	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDefaultPytestStatuses_MatchTheDTestTab(t *testing.T) {
	t.Parallel()
	got := services.DefaultPytestStatuses()
	assert.ElementsMatch(t, []string{
		"failure", "error", "passed & error", "failure & error", "skipped & error", "error & error",
	}, got)
	for _, hidden := range []string{"passed", "skipped", "xfailed", "xpass"} {
		assert.NotContains(t, got, hidden)
	}
	assert.Subset(t, services.PytestStatuses, got)
}

func TestParsePytestStatuses_ValidatesAndNormalises(t *testing.T) {
	t.Parallel()
	got, err := services.ParsePytestStatuses([]string{" Failure", "skipped & error", ""})
	require.NoError(t, err)
	assert.Equal(t, []string{"failure", "skipped & error"}, got)

	_, err = services.ParsePytestStatuses([]string{"failure", "failed"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), `unknown status "failed"`)
	assert.Contains(t, err.Error(), "xpass")
}
