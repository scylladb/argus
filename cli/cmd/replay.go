package cmd

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/scylladb/argus/cli/internal/replay"
	"github.com/spf13/cobra"
)

var replayCmd = &cobra.Command{
	Use:   "replay",
	Short: "Replay captured Argus API requests from JSONL log files",
	Long: `Upload one or more argus_replay_log_*.jsonl files to the Argus
replay-ingest endpoint so the server can re-apply every captured request.

Accepted input shapes for --file (any combination):
  * plain .jsonl                                     – a single replay log
  * .jsonl.zst / .jsonl.zstd                         – zstd-compressed replay log
  * .tar.zst / .tar.zstd                             – an archive whose entries
                                                       matching argus_replay_log_*.jsonl
                                                       are extracted and replayed

The CLI normalises every input into a single tar.zst archive and streams it
to POST /api/v1/client/replay/ingest. The server merges and sorts records by
timestamp, applies idempotency classification per endpoint, and returns a
summary of what was replayed.

Use --dir to scan a directory for argus_replay_log_*.jsonl (and .jsonl.zst)
files; use --run-id to filter by the run encoded in the filename — the
filter also applies to entries inside tar.zst archives. --dry-run asks the
server to validate the archive and return the summary without executing any
side effects. Use --target-url to replay against a different Argus instance;
you must already hold credentials valid for that target (the CLI does not
re-authenticate against a different host).`,
	Example: `  # Replay all files for a run from the SCT results directory
  argus run replay --dir ~/sct-results/latest --run-id 550e8400-e29b-41d4-a716-446655440000

  # Replay an SCT events bundle directly
  argus run replay --file ~/sct-extract/sct-runner-events-abc.tar.zst

  # Replay a compressed single log
  argus run replay --file argus_replay_log_R_1.jsonl.zst

  # Dry-run preview
  argus run replay --dir ~/sct-results/latest --run-id 550e... --dry-run`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "run-replay")

		dir, _ := cmd.Flags().GetString("dir")
		runID, _ := cmd.Flags().GetString("run-id")
		fileArgs, _ := cmd.Flags().GetStringArray("file")
		dryRun, _ := cmd.Flags().GetBool("dry-run")
		createMissingTests, _ := cmd.Flags().GetBool("create-missing-tests")
		targetURL, _ := cmd.Flags().GetString("target-url")
		reportFmt, _ := cmd.Flags().GetString("report")

		inputs, err := collectFiles(dir, runID, fileArgs)
		if err != nil {
			log.Error().Err(err).Msg("failed to collect replay files")
			return err
		}

		files, cleanup, err := materializeInputs(inputs, runID, log)
		defer cleanup()
		if err != nil {
			log.Error().Err(err).Msg("failed to materialize input files")
			return err
		}

		log.Info().Int("file_count", len(files)).Bool("dry_run", dryRun).Msg("starting replay upload")

		client, err := replayClient(ctx, targetURL)
		if err != nil {
			return err
		}

		summary, err := uploadReplay(ctx, client, files, dryRun, createMissingTests, log)
		if err != nil {
			return err
		}

		return renderReplaySummary(cmd, reportFmt, summary)
	},
}

// materializeInputs runs Materialize on every input path and returns the
// flattened list of JSONL paths plus a combined cleanup. cleanup is always
// non-nil and safe to call on the error path.
func materializeInputs(inputs []string, runID string, log zerolog.Logger) ([]string, func(), error) {
	cleanups := make([]func(), 0, len(inputs))
	cleanup := func() {
		for _, c := range cleanups {
			c()
		}
	}

	var files []string
	for _, in := range inputs {
		mi, err := replay.Materialize(in, runID)
		if mi != nil && mi.Cleanup != nil {
			cleanups = append(cleanups, mi.Cleanup)
		}
		if err != nil {
			return nil, cleanup, err
		}
		log.Debug().Str("input", in).Int("yielded", len(mi.Files)).Msg("materialized input")
		files = append(files, mi.Files...)
	}

	if len(files) == 0 {
		return nil, cleanup, errors.New("no replay log files to upload after filtering")
	}
	// Deterministic upload order, regardless of input order.
	sort.Strings(files)
	return files, cleanup, nil
}

// collectFiles resolves the --dir/--run-id/--file flags into a deterministic
// list of input paths. The returned paths still need to pass through
// replay.Materialize: tar.zst archives and .jsonl.zst inputs are decoded by
// the materialization step, not here.
func collectFiles(dir, runID string, fileArgs []string) ([]string, error) {
	if dir != "" && len(fileArgs) > 0 {
		return nil, errors.New("--dir and --file are mutually exclusive")
	}
	if dir == "" && len(fileArgs) == 0 {
		return nil, errors.New("one of --dir or --file is required")
	}

	if len(fileArgs) > 0 {
		// Deduplicate while preserving the user's order on first occurrence.
		// --run-id is applied during materialisation so it remains effective
		// for tar.zst inputs that contain multiple runs.
		seen := make(map[string]struct{}, len(fileArgs))
		out := make([]string, 0, len(fileArgs))
		for _, p := range fileArgs {
			if _, ok := seen[p]; ok {
				continue
			}
			seen[p] = struct{}{}
			out = append(out, p)
		}
		return out, nil
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("reading %q: %w", dir, err)
	}

	// --dir scans for both plain JSONL and zstd-compressed JSONL replay
	// logs. tar.zst archives are not picked up here because they typically
	// live elsewhere (event-bundle directories) and the user passes them
	// explicitly with --file.
	var matched []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		m := replay.ReplayFileNamePattern.FindStringSubmatch(e.Name())
		if m == nil {
			continue
		}
		if runID != "" && m[replay.ReplayFileNamePattern.SubexpIndex("run")] != runID {
			continue
		}
		matched = append(matched, filepath.Join(dir, e.Name()))
	}

	if len(matched) == 0 {
		if runID != "" {
			return nil, fmt.Errorf("no argus_replay_log_%s_*.jsonl[.zst] files in %q", runID, dir)
		}
		return nil, fmt.Errorf("no argus_replay_log_*.jsonl[.zst] files in %q", dir)
	}

	sort.Strings(matched)
	return matched, nil
}

// replayClient returns the API client to use for the upload. When targetURL is
// empty the context's client is reused; otherwise a fresh client is built
// against targetURL using the same credential discovery as the root command.
func replayClient(ctx context.Context, targetURL string) (*api.Client, error) {
	if targetURL == "" {
		return APIClientFrom(ctx), nil
	}

	if _, err := url.ParseRequestURI(targetURL); err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrInvalidURL, targetURL, err)
	}

	baseCfg := ConfigFrom(ctx)
	cfg := &config.Config{
		URL:   targetURL,
		UseCf: baseCfg.UseCf,
	}
	if isLoopbackURL(targetURL) {
		cfg.UseCf = false
	}

	client, err := buildAPIClientRaw(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return client, nil
}

// uploadReplay streams the tar.zst archive of files to the replay-ingest
// endpoint and decodes the server's summary response.
func uploadReplay(
	ctx context.Context,
	client *api.Client,
	files []string,
	dryRun bool,
	createMissingTests bool,
	log zerolog.Logger,
) (*models.ReplayIngestSummary, error) {
	route := api.ReplayIngest
	q := url.Values{}
	if dryRun {
		q.Set("dry_run", "true")
	}
	if createMissingTests {
		q.Set("create_missing_tests", "true")
	}
	if encoded := q.Encode(); encoded != "" {
		route += "?" + encoded
	}

	pr, pw := io.Pipe()

	// Pack into pw on a goroutine; the HTTP body reads from pr. If Pack
	// returns an error (most commonly ErrInvalidJSONL from pre-validation),
	// CloseWithError propagates it so the HTTP request fails and the goroutine
	// outcome surfaces below.
	packErrCh := make(chan error, 1)
	go func() {
		defer close(packErrCh)
		err := replay.Pack(files, pw)
		if err != nil {
			_ = pw.CloseWithError(err)
			packErrCh <- err
			return
		}
		_ = pw.Close()
	}()

	req, err := client.NewRequest(ctx, "POST", route, nil)
	if err != nil {
		_ = pr.Close()
		<-packErrCh
		return nil, err
	}
	req.Body = pr
	req.Header.Set("Content-Type", "application/x-tar-zstd")

	resp, err := client.DoStream(req)
	if packErr := <-packErrCh; packErr != nil {
		if resp != nil {
			_, _ = io.Copy(io.Discard, resp.Body)
			_ = resp.Body.Close()
		}
		return nil, packErr
	}
	if err != nil {
		return nil, fmt.Errorf("replay upload: %w", err)
	}

	// Backend always returns HTTP 200 with the standard error envelope for
	// validation/server failures (see argus/backend/error_handlers.py).
	// The shared decoder handles the success path, the envelope-error path,
	// and the 401/403 auth-retry signal uniformly with the rest of the CLI.
	summary, err := api.DecodeResponse[models.ReplayIngestSummary](resp)
	if err != nil {
		return nil, err
	}
	log.Info().
		Int("total", summary.Total).
		Int("succeeded", summary.Succeeded).
		Int("failed", summary.Failed).
		Int("skipped", summary.SkippedNoReplay).
		Msg("replay upload complete")
	return &summary, nil
}

// renderReplaySummary writes the summary either as JSON (--report json or the
// default JSON output mode) or as a human-readable one-liner plus, when
// non-empty, an errors table.
func renderReplaySummary(cmd *cobra.Command, reportFmt string, summary *models.ReplayIngestSummary) error {
	ctx := cmd.Context()
	out := OutputterFrom(ctx)

	switch strings.ToLower(reportFmt) {
	case "", "text":
		_, _ = fmt.Fprintf(cmd.OutOrStdout(),
			"Replay summary: total=%d processed=%d succeeded=%d failed=%d skipped=%d\n",
			summary.Total, summary.Processed, summary.Succeeded, summary.Failed, summary.SkippedNoReplay,
		)
		if len(summary.Errors) == 0 {
			return nil
		}
		// Reuse the text outputter for the errors table.
		text := output.New(cmd.OutOrStdout(), true)
		return text.Write(models.NewTabularSlice(summary.Errors))
	case "json":
		return out.Write(summary)
	default:
		return fmt.Errorf("--report: unknown format %q (expected \"text\" or \"json\")", reportFmt)
	}
}

func init() {
	replayCmd.Flags().String("dir", "", "Directory to scan for argus_replay_log_*.jsonl files")
	replayCmd.Flags().String("run-id", "", "Filter by run UUID (used with --dir)")
	replayCmd.Flags().StringArray("file", nil, "Explicit JSONL file path (repeatable; mutually exclusive with --dir)")
	replayCmd.Flags().Bool("dry-run", false, "Have the server validate without executing")
	replayCmd.Flags().Bool("create-missing-tests", false,
		"Ask the server to auto-create ArgusRelease/Group/Test rows for build_ids "+
			"that have no curated test entity yet (parsed from build_id as release/group/test). "+
			"When false (default), submit_run records whose test entity does not yet exist "+
			"are reported as failures naming the would-be release/group/test and which level "+
			"is missing -- rather than silently inserting a broken run with empty test_id.")
	replayCmd.Flags().String("target-url", "", "Override the base URL (replay against a different Argus instance)")
	replayCmd.Flags().String("report", "text", `Output format: "text" or "json"`)

	replayCmd.MarkFlagsMutuallyExclusive("dir", "file")

	runCmd.AddCommand(replayCmd)
}
