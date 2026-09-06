package cmd

import (
	"strings"
	"testing"
)

func TestResultsRouteIncludeHidden(t *testing.T) {
	testID := "11111111-1111-1111-1111-111111111111"
	runID := "22222222-2222-2222-2222-222222222222"

	base := resultsRoute(testID, runID, false)
	if strings.Contains(base, "?") {
		t.Errorf("default route must carry no query params, got %s", base)
	}
	if want := "/api/v1/run/" + testID + "/" + runID + "/fetch_results"; base != want {
		t.Errorf("resultsRoute(false) = %s, want %s", base, want)
	}

	hidden := resultsRoute(testID, runID, true)
	if want := base + "?includeHidden=true"; hidden != want {
		t.Errorf("resultsRoute(true) = %s, want %s", hidden, want)
	}
}

func TestResultsCmdHasShowHiddenFlag(t *testing.T) {
	f := resultsCmd.Flags().Lookup("show-hidden")
	if f == nil {
		t.Fatal("results command is missing the --show-hidden flag")
	}
	if f.DefValue != "false" {
		t.Errorf("--show-hidden default = %s, want false", f.DefValue)
	}
	if f.Usage == "" {
		t.Error("--show-hidden is missing help text")
	}
}
