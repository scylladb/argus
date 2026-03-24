package cmd

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// PytestView is a single pytest result for output.
type PytestView struct {
	Name     string  `json:"name"`
	Status   string  `json:"status"`
	Duration float64 `json:"duration,omitempty"`
	Message  string  `json:"message,omitempty"`
}

// PytestResultsView is the top-level pytest output.
type PytestResultsView struct {
	TotalTests  int          `json:"total_tests"`
	FailedCount int          `json:"failed_count"`
	FailedTests []PytestView `json:"failed_tests"`
}

// Headers implements output.Tabular.
func (v *PytestResultsView) Headers() []string {
	return []string{"Name", "Status", "Duration", "Message"}
}

// Rows implements output.Tabular.
func (v *PytestResultsView) Rows() [][]string {
	rows := [][]string{
		{"[summary]", fmt.Sprintf("total=%d failed=%d", v.TotalTests, v.FailedCount), "", ""},
	}
	for _, t := range v.FailedTests {
		msg := t.Message
		if len(msg) > 100 {
			msg = msg[:100] + "..."
		}
		rows = append(rows, []string{
			t.Name, t.Status, fmt.Sprintf("%.2f", t.Duration), msg,
		})
	}
	return rows
}

var runTestsCmd = &cobra.Command{
	Use:   "tests <run_id>",
	Short: "Pytest results with failure details (DTest only)",
	Long: `Fetch pytest results for a DTest run.

Shows total test count and failed tests with details.
SCT runs have no pytest results — use 'argus run events' instead.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)

		runID, err := parseRunID(args[0])
		if err != nil {
			return err
		}

		info, err := fetchRunInfo(ctx, client, c, runID)
		if err != nil {
			return err
		}
		if info.IsSCT() {
			return fmt.Errorf("pytest results are only available for DTest runs; use 'argus run events' for SCT")
		}

		// Fetch pytest results (with cache).
		cacheKey := fmt.Sprintf("pytest_results_%s.json", runID)
		var results []models.PytestResult

		if data := c.Get(cacheKey); data != nil {
			_ = json.Unmarshal(data, &results)
		}

		if results == nil {
			path := fmt.Sprintf("/api/v1/run/%s/pytest/results", runID)
			req, err := client.NewRequest(ctx, "GET", path, nil)
			if err != nil {
				return err
			}
			results, err = api.DoJSON[[]models.PytestResult](client, req)
			if err != nil {
				return fmt.Errorf("fetching pytest results: %w", err)
			}
			if raw, marshalErr := json.Marshal(results); marshalErr == nil {
				_ = c.Set(cacheKey, raw)
			}
		}

		skipStatuses := map[string]bool{
			"passed":  true,
			"xpass":   true,
			"skipped": true,
			"xfailed": true,
		}

		var failed []PytestView
		for _, r := range results {
			status := strings.ToLower(string(r.Status))
			if skipStatuses[status] {
				continue
			}
			failed = append(failed, PytestView{
				Name:     r.Name,
				Status:   string(r.Status),
				Duration: r.Duration,
				Message:  r.Message,
			})
		}

		if failed == nil {
			failed = []PytestView{}
		}

		return out.Write(&PytestResultsView{
			TotalTests:  len(results),
			FailedCount: len(failed),
			FailedTests: failed,
		})
	},
}
