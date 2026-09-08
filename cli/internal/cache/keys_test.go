package cache

import (
	"path"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestResultsKeySeparatesHiddenColumnVariants(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	visible := ResultsKey(testID, runID, false)
	all := ResultsKey(testID, runID, true)

	require.NotEqual(t, all, visible, "hidden-column variants share a cache key")
	assert.Equal(t, "results/"+testID+"/visible/"+runID, visible)
	assert.Equal(t, "results/"+testID+"/all/"+runID, all)
}

// A pre-upgrade CLI keyed this entry as results/{testID}/{runID}, so that
// directory can still hold a legacy meta.json. findLeaves stops descending at
// the first meta.json, and PurgeExpired removes the whole entry directory — so
// a variant nested under the legacy leaf would be invisible to Stats and would
// be deleted along with it. Neither variant may live under that path.
func TestResultsKeyStaysOutsideLegacyEntryDir(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	legacy := path.Join("results", testID, runID)
	for _, includeHidden := range []bool{false, true} {
		key := ResultsKey(testID, runID, includeHidden)
		assert.NotEqual(t, legacy, key, "includeHidden=%t", includeHidden)
		assert.False(t, strings.HasPrefix(key, legacy+"/"),
			"ResultsKey(%t) = %s, must not sit under the legacy entry dir %s", includeHidden, key, legacy)
	}
}

// Reproduces the upgrade scenario end to end through the real Stats and
// PurgeExpired: a legacy results/{testID}/{runID} entry left by an older CLI
// must not swallow or destroy the new variant entries.
func TestResultsKeySurvivesLegacyEntryPurge(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	c := New(t.TempDir())

	// A legacy entry written by a pre-upgrade CLI, already expired.
	legacyKey := path.Join("results", testID, runID)
	require.NoError(t, Set(c, legacyKey, map[string]string{"stale": "yes"}, "/legacy", time.Nanosecond))

	// Fresh entries written by this version, with plenty of TTL left.
	visibleKey := ResultsKey(testID, runID, false)
	allKey := ResultsKey(testID, runID, true)
	for _, k := range []string{visibleKey, allKey} {
		require.NoError(t, Set(c, k, map[string]string{"fresh": "yes"}, "/fresh", time.Hour), "seeding %s", k)
	}

	// Stats must see all three entries, not just the legacy leaf.
	stats, err := c.Stats()
	require.NoError(t, err)
	assert.Equal(t, 3, stats.Entries, "new variants hidden behind the legacy leaf?")

	// Purging the expired legacy entry must leave the fresh variants intact.
	assert.Equal(t, 1, c.PurgeExpired(), "PurgeExpired must remove only the legacy entry")
	for _, k := range []string{visibleKey, allKey} {
		_, _, err := Get[map[string]string](c, k)
		assert.NoError(t, err, "entry %s was destroyed by the legacy purge", k)
	}
}
