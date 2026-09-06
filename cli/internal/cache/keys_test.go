package cache

import (
	"path"
	"strings"
	"testing"
	"time"
)

func TestResultsKeySeparatesHiddenColumnVariants(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	visible := ResultsKey(testID, runID, false)
	all := ResultsKey(testID, runID, true)

	if visible == all {
		t.Fatalf("hidden-column variants share a cache key: %s", visible)
	}
	if want := "results/" + testID + "/visible/" + runID; visible != want {
		t.Errorf("ResultsKey(false) = %s, want %s", visible, want)
	}
	if want := "results/" + testID + "/all/" + runID; all != want {
		t.Errorf("ResultsKey(true) = %s, want %s", all, want)
	}
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
		if key == legacy || strings.HasPrefix(key, legacy+"/") {
			t.Errorf("ResultsKey(%t) = %s, must not sit under the legacy entry dir %s",
				includeHidden, key, legacy)
		}
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
	if err := Set(c, legacyKey, map[string]string{"stale": "yes"}, "/legacy", time.Nanosecond); err != nil {
		t.Fatalf("seeding legacy entry: %v", err)
	}

	// Fresh entries written by this version, with plenty of TTL left.
	visibleKey := ResultsKey(testID, runID, false)
	allKey := ResultsKey(testID, runID, true)
	for _, k := range []string{visibleKey, allKey} {
		if err := Set(c, k, map[string]string{"fresh": "yes"}, "/fresh", time.Hour); err != nil {
			t.Fatalf("seeding %s: %v", k, err)
		}
	}

	// Stats must see all three entries, not just the legacy leaf.
	stats, err := c.Stats()
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if stats.Entries != 3 {
		t.Errorf("Stats saw %d entries, want 3 (new variants hidden behind the legacy leaf?)", stats.Entries)
	}

	// Purging the expired legacy entry must leave the fresh variants intact.
	if removed := c.PurgeExpired(); removed != 1 {
		t.Errorf("PurgeExpired removed %d entries, want 1", removed)
	}
	for _, k := range []string{visibleKey, allKey} {
		if _, _, err := Get[map[string]string](c, k); err != nil {
			t.Errorf("entry %s was destroyed by the legacy purge: %v", k, err)
		}
	}
}
