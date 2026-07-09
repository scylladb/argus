package test

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerCheckQueue adds the "check-queue" sub-command to parent.
func registerCheckQueue(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "check-queue",
		Short: "Query the status of Jenkins queue items",
		Long: `Report the current state of one or more Jenkins queue items: whether
each has been scheduled onto an executor (with its build URL) or is still waiting
in the queue (with the reason why).

Queue items are supplied with repeatable --item flags and/or a --file containing
the JSON emitted by 'test execute' — either {"queueItem": 123} or
{"queueItem": [123, 456]}. Use "-" to read that JSON from standard input:

  argus test check-queue --item 123 --item 456
  argus test check-queue --file queued.json
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb \
    | argus test check-queue --file -

This is a one-shot snapshot; it does not wait for pending items to start.`,
		RunE: runCheckQueue,
	}

	cmd.Flags().IntSlice("item", nil, "Queue item to query (repeatable; also accepts a comma-separated list)")
	cmd.Flags().StringP("file", "f", "", "JSON {\"queueItem\": N|[...]} with queue items (\"-\" for stdin)")

	parent.AddCommand(cmd)
}

// runCheckQueue is the RunE handler for "test check-queue".
func runCheckQueue(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "test-check-queue")

	items, err := collectQueueItems(cmd)
	if err != nil {
		return err
	}
	log.Debug().Int("count", len(items)).Msg("querying queue items")

	svc := services.NewTestExecutionService(client, c)

	// Query each item independently; a per-item failure is recorded in its row
	// and never aborts the batch.
	results := make(models.QueueStatuses, 0, len(items))
	for _, item := range items {
		row := models.QueueStatus{QueueItem: item}
		info, err := svc.QueueInfo(ctx, item)
		switch {
		case err != nil:
			log.Error().Err(err).Int("queue_item", item).Msg("failed to fetch queue info")
			row.Status = "error: " + err.Error()
		case info.Scheduled():
			row.Status = "started"
			row.URL = info.URL
			row.Number = info.Number
		default:
			row.Status = "pending"
			row.Why = info.Why
		}
		results = append(results, row)
	}

	return out.Write(results)
}

// collectQueueItems gathers the queue items to query from the repeatable --item
// flag and the optional --file JSON, then de-duplicates and sorts them
// ascending for deterministic output. At least one source must be supplied.
func collectQueueItems(cmd *cobra.Command) ([]int, error) {
	flagItems, _ := cmd.Flags().GetIntSlice("item")

	var fileItems []int
	if path, _ := cmd.Flags().GetString("file"); path != "" {
		raw, err := readFileOrStdin(path)
		if err != nil {
			return nil, fmt.Errorf("reading queue items file: %w", err)
		}
		fileItems, err = parseQueueItems(raw)
		if err != nil {
			return nil, err
		}
	}

	if len(flagItems) == 0 && len(fileItems) == 0 {
		return nil, fmt.Errorf("provide queue items with --item or --file")
	}

	seen := make(map[int]struct{}, len(flagItems)+len(fileItems))
	items := make([]int, 0, len(flagItems)+len(fileItems))
	for _, group := range [][]int{flagItems, fileItems} {
		for _, item := range group {
			if _, ok := seen[item]; ok {
				continue
			}
			seen[item] = struct{}{}
			items = append(items, item)
		}
	}
	sort.Ints(items)
	return items, nil
}

// parseQueueItems parses the {"queueItem": N | [...]} JSON produced by
// 'test execute' into a list of queue items. The queueItem value may be a
// single number or an array of numbers; a missing key yields no items.
func parseQueueItems(raw []byte) ([]int, error) {
	var envelope struct {
		QueueItem json.RawMessage `json:"queueItem"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return nil, fmt.Errorf("parsing queue items (expected {\"queueItem\": N|[...]}): %w", err)
	}
	if len(envelope.QueueItem) == 0 {
		return nil, nil
	}

	var list []int
	if err := json.Unmarshal(envelope.QueueItem, &list); err == nil {
		return list, nil
	}
	var single int
	if err := json.Unmarshal(envelope.QueueItem, &single); err != nil {
		return nil, fmt.Errorf("parsing queueItem (expected a number or array of numbers): %w", err)
	}
	return []int{single}, nil
}
