package cache

import "testing"

func TestResultsKeySeparatesHiddenColumnVariants(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	visible := ResultsKey(testID, runID, false)
	all := ResultsKey(testID, runID, true)

	if visible == all {
		t.Fatalf("hidden-column variants share a cache key: %s", visible)
	}
	if want := "results/" + testID + "/" + runID + "/visible"; visible != want {
		t.Errorf("ResultsKey(false) = %s, want %s", visible, want)
	}
	if want := "results/" + testID + "/" + runID + "/all"; all != want {
		t.Errorf("ResultsKey(true) = %s, want %s", all, want)
	}
}
