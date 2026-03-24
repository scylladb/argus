package cmd

import (
	"fmt"
	"time"

	"github.com/spf13/cobra"
)

// NemesisView is a single nemesis execution for output.
type NemesisView struct {
	Name       string `json:"name"`
	Status     string `json:"status"`
	TargetNode string `json:"target_node"`
	StartTime  string `json:"start_time"`
	EndTime    string `json:"end_time"`
	Duration   string `json:"duration"`
	StackTrace string `json:"stack_trace,omitempty"`
}

// NemesisListView wraps a slice of NemesisView for output.
type NemesisListView struct {
	Nemeses []NemesisView `json:"nemeses"`
}

// Headers implements output.Tabular.
func (v *NemesisListView) Headers() []string {
	return []string{"Name", "Status", "TargetNode", "StartTime", "EndTime", "Duration"}
}

// Rows implements output.Tabular.
func (v *NemesisListView) Rows() [][]string {
	rows := make([][]string, 0, len(v.Nemeses))
	for _, n := range v.Nemeses {
		rows = append(rows, []string{
			n.Name, n.Status, n.TargetNode,
			n.StartTime, n.EndTime, n.Duration,
		})
	}
	return rows
}

var (
	nemesesAfter  string
	nemesesBefore string
)

var runNemesesCmd = &cobra.Command{
	Use:   "nemeses <run_id>",
	Short: "Nemesis executions with status and targets (SCT only)",
	Long: `List all nemesis executions for an SCT run.

Each nemesis includes: name, status (succeeded/failed/skipped),
target node, start/end times, duration, and stack trace (if failed).

Use --after and --before to filter nemeses by start time.`,
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
		if !info.IsSCT() {
			return fmt.Errorf("nemeses are only available for SCT runs")
		}

		afterUnix, err := parseTimeFlag(nemesesAfter)
		if err != nil {
			return fmt.Errorf("--after: %w", err)
		}
		beforeUnix, err := parseTimeFlag(nemesesBefore)
		if err != nil {
			return fmt.Errorf("--before: %w", err)
		}

		r := info.SCT
		result := make([]NemesisView, 0, len(r.NemesisData))
		for _, nem := range r.NemesisData {
			if afterUnix > 0 && nem.StartTime < afterUnix {
				continue
			}
			if beforeUnix > 0 && nem.StartTime > beforeUnix {
				continue
			}
			targetNode := ""
			if nem.TargetNode != nil {
				targetNode = nem.TargetNode.Name
			}

			duration := ""
			if nem.StartTime > 0 && nem.EndTime > 0 {
				d := time.Duration(nem.EndTime-nem.StartTime) * time.Second
				duration = d.String()
			}

			result = append(result, NemesisView{
				Name:       nem.Name,
				Status:     nem.Status,
				TargetNode: targetNode,
				StartTime:  formatTimestamp(nem.StartTime),
				EndTime:    formatTimestamp(nem.EndTime),
				Duration:   duration,
				StackTrace: nem.StackTrace,
			})
		}

		return out.Write(&NemesisListView{Nemeses: result})
	},
}

func init() {
	runNemesesCmd.Flags().StringVar(&nemesesAfter, "after", "", "show nemeses starting after this time (unix timestamp or RFC3339)")
	runNemesesCmd.Flags().StringVar(&nemesesBefore, "before", "", "show nemeses starting before this time (unix timestamp or RFC3339)")
}
