package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var (
	eventsLimit  int
	eventsAfter  string
	eventsBefore string
)

// EventView is a single event for output.
type EventView struct {
	Severity  string `json:"severity"`
	EventType string `json:"event_type"`
	Message   string `json:"message"`
	Timestamp string `json:"timestamp"`
	Node      string `json:"node,omitempty"`
}

// EventListView wraps a slice of EventView for output.
type EventListView struct {
	Events []EventView `json:"events"`
}

// Headers implements output.Tabular.
func (v *EventListView) Headers() []string {
	return []string{"Severity", "EventType", "Timestamp", "Node", "Message"}
}

// Rows implements output.Tabular.
func (v *EventListView) Rows() [][]string {
	rows := make([][]string, 0, len(v.Events))
	for _, e := range v.Events {
		msg := e.Message
		if len(msg) > 120 {
			msg = msg[:120] + "..."
		}
		rows = append(rows, []string{
			e.Severity,
			e.EventType,
			e.Timestamp,
			e.Node,
			msg,
		})
	}
	return rows
}

var runEventsCmd = &cobra.Command{
	Use:   "events <run_id>",
	Short: "ERROR/CRITICAL events (SCT only)",
	Long: `Fetch and display error events for an SCT run.

Only ERROR and CRITICAL severity events are shown. Each event includes:
severity, event type, timestamp, node, and message.

Use --after and --before to filter events by time period.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)

		runID, err := parseRunID(args[0])
		if err != nil {
			return err
		}

		beforeUnix, err := parseTimeFlag(eventsBefore)
		if err != nil {
			return fmt.Errorf("--before: %w", err)
		}

		afterUnix, err := parseTimeFlag(eventsAfter)
		if err != nil {
			return fmt.Errorf("--after: %w", err)
		}

		critEvents, err := fetchEventsBySeverity(ctx, client, runID, "CRITICAL", eventsLimit, beforeUnix)
		if err != nil {
			return err
		}
		errEvents, err := fetchEventsBySeverity(ctx, client, runID, "ERROR", eventsLimit, beforeUnix)
		if err != nil {
			return err
		}
		events := append(critEvents, errEvents...)

		result := make([]EventView, 0, len(events))
		for _, evt := range events {
			if afterUnix > 0 {
				ts, tsErr := parseEventTimestamp(evt.Ts)
				if tsErr == nil && ts < afterUnix {
					continue
				}
			}

			result = append(result, EventView{
				Severity:  string(evt.Severity),
				EventType: evt.EventType,
				Message:   evt.Message,
				Timestamp: formatTimestamp(evt.Ts),
				Node:      evt.Node,
			})
		}

		return out.Write(&EventListView{Events: result})
	},
}

func init() {
	runEventsCmd.Flags().IntVar(&eventsLimit, "limit", 100, "maximum number of events per severity")
	runEventsCmd.Flags().StringVar(&eventsAfter, "after", "", "show events after this time (unix timestamp or RFC3339)")
	runEventsCmd.Flags().StringVar(&eventsBefore, "before", "", "show events before this time (unix timestamp or RFC3339)")
}
