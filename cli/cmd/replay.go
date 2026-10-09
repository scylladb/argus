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
	"strconv"
	"strings"
	"unicode"

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
side effects. After replaying, the server lists each run's S3 log prefix and
attaches any log archives that were uploaded but whose logs/submit was never
recorded (e.g. loader/monitor/sct-runner bundles); pass --backfill-logs=false
to skip that step. Use --target-url to replay against a different Argus
instance; you must already hold credentials valid for that target (the CLI
does not re-authenticate against a different host).

A local run (one run with no Jenkins build URL) goes to
local-runs/<your Argus username>/<job> by default, where <job> is its first
SCT config file, e.g. local-runs/jdoe/longevity-100gb-4h. Use --build-id to
pick another build path, e.g. scylla-staging/<user>/<job>. Either way the
server gives each run a new run ID, so every replay makes a new run, and
recorded log links keep pointing at the original S3 objects. Each run takes
the next free build number under the path; end --build-id with #<n> to
choose it. For a replay into a build path, --as-me is on unless you turn it
off, so the run belongs to your Argus user. The local-runs default also
creates its release, group and test; --build-id creates a missing group and
test only with --create-missing-tests. The new run records the original run ID, and its page links
to the original run. Use --resume <run-id> to finish a --build-id replay that
failed, in the run it made. Use --keep-run to replay a local run as
recorded. --build-id must name an existing release; only the local-runs
default creates its release. Without a build path, --as-me only makes you the
assignee, and the run keeps its recorded starter.

The summary lists each run with its Argus link. A retargeted run shows the
run ID from the log next to the new one.`,
	Example: `  # Replay all files for a run from the SCT results directory
  argus run replay --dir ~/sct-results/latest --run-id 550e8400-e29b-41d4-a716-446655440000

  # Replay an SCT events bundle directly
  argus run replay --file ~/sct-extract/sct-runner-events-abc.tar.zst

  # Replay without the default S3 log-link back-fill
  argus run replay --file ~/sct-extract/sct-runner-events-abc.tar.zst --backfill-logs=false

  # Replay a compressed single log
  argus run replay --file argus_replay_log_R_1.jsonl.zst

  # Replay into your own folder as a new run that you own
  argus run replay --file ~/sct-extract/sct-runner-events-abc.tar.zst \
    --build-id scylla-staging/jdoe/my-argus-local-run

  # The same, but keep the scheduled assignee and the recorded starter
  argus run replay --file ~/sct-extract/sct-runner-events-abc.tar.zst \
    --build-id scylla-staging/jdoe/my-argus-local-run --as-me=false

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
		createMissingTests := optionalBool(cmd, "create-missing-tests")
		backfillLogs, _ := cmd.Flags().GetBool("backfill-logs")
		targetURL, _ := cmd.Flags().GetString("target-url")
		reportFmt, _ := cmd.Flags().GetString("report")
		buildID, _ := cmd.Flags().GetString("build-id")
		asMe := optionalBool(cmd, "as-me")
		resumeRunID, _ := cmd.Flags().GetString("resume")

		if buildID != "" {
			if err := checkBuildID(buildID); err != nil {
				return err
			}
		}
		keepRun, _ := cmd.Flags().GetBool("keep-run")

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

		opts := replayOptions{
			DryRun:             dryRun,
			CreateMissingTests: createMissingTests,
			BackfillLogs:       backfillLogs,
			BuildID:            buildID,
			AsMe:               asMe,
			ResumeRunID:        resumeRunID,
			KeepRun:            keepRun,
		}
		summary, err := uploadReplay(ctx, client, files, opts, log)
		if err != nil {
			return err
		}

		report := replayReport{ReplayIngestSummary: summary, Runs: runLinks(client.BaseURL(), summary.Runs, dryRun)}
		return renderReplaySummary(cmd, reportFmt, report)
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

// replayOptions are the query parameters of one replay-ingest request. A nil
// CreateMissingTests or AsMe leaves the choice to the server, which turns both
// on for a replay with a build ID.
type replayOptions struct {
	DryRun             bool
	CreateMissingTests *bool
	BackfillLogs       bool
	BuildID            string
	AsMe               *bool
	ResumeRunID        string
	KeepRun            bool
}

// checkBuildID applies the server's rule for a build ID before the archive
// is uploaded: a path of two or more slash-separated names, none empty, none
// holding whitespace, and an optional "#<n>" build number above zero. The
// server also checks that the build number is free.
func checkBuildID(buildID string) error {
	path, number, hasNumber := strings.Cut(buildID, "#")
	parts := strings.Split(path, "/")
	if len(parts) < 2 {
		return fmt.Errorf("--build-id %q: name a release and a test, e.g. scylla-staging/<user>/<job>", buildID)
	}
	for _, p := range parts {
		if p == "" || strings.IndexFunc(p, unicode.IsSpace) >= 0 {
			return fmt.Errorf("--build-id %q: every name must be non-empty and hold no whitespace", buildID)
		}
	}
	if hasNumber {
		if n, err := strconv.Atoi(number); err != nil || n < 1 || strconv.Itoa(n) != number {
			return fmt.Errorf("--build-id %q: the build number after '#' must be a positive integer", buildID)
		}
	}
	return nil
}

// optionalBool returns the value of a bool flag the user set, or nil.
func optionalBool(cmd *cobra.Command, name string) *bool {
	if !cmd.Flags().Changed(name) {
		return nil
	}
	v, _ := cmd.Flags().GetBool(name)
	return &v
}

// uploadReplay streams the tar.zst archive of files to the replay-ingest
// endpoint and decodes the server's summary response.
func uploadReplay(
	ctx context.Context,
	client *api.Client,
	files []string,
	opts replayOptions,
	log zerolog.Logger,
) (*models.ReplayIngestSummary, error) {
	route := api.ReplayIngest
	q := url.Values{}
	if opts.DryRun {
		q.Set("dry_run", "true")
	}
	if opts.CreateMissingTests != nil {
		q.Set("create_missing_tests", strconv.FormatBool(*opts.CreateMissingTests))
	}
	// Backfill is on by default server-side; only send the param to disable it.
	if !opts.BackfillLogs {
		q.Set("backfill_logs", "false")
	}
	if opts.BuildID != "" {
		q.Set("build_id", opts.BuildID)
	}
	if opts.AsMe != nil {
		q.Set("as_me", strconv.FormatBool(*opts.AsMe))
	}
	if opts.ResumeRunID != "" {
		q.Set("resume_run_id", opts.ResumeRunID)
	}
	// The CLI asks for the local-runs default unless the user keeps the run.
	if !opts.KeepRun {
		q.Set("local_runs", "true")
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
	packErr := <-packErrCh
	// io.ErrClosedPipe means the HTTP side closed the body before it read all
	// of it: the request was rejected, or the server answered early. err or
	// resp holds the cause.
	bodyCut := errors.Is(packErr, io.ErrClosedPipe)
	if packErr != nil && !bodyCut {
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
	if bodyCut {
		return nil, fmt.Errorf("replay upload: server answered before it read the whole archive: %w", packErr)
	}
	log.Info().
		Int("total", summary.Total).
		Int("succeeded", summary.Succeeded).
		Int("failed", summary.Failed).
		Int("skipped", summary.SkippedNoReplay).
		Int("backfilled_logs", summary.BackfilledLogs).
		Msg("replay upload complete")
	return &summary, nil
}

// replayRunLink is the Argus web link of one run that the replay touched.
type replayRunLink struct {
	Type        string `json:"type"`
	ID          string `json:"id"`
	SourceID    string `json:"source_id"`
	BuildID     string `json:"build_id,omitempty"`
	BuildNumber *int   `json:"build_number,omitempty"`
	URL         string `json:"url,omitempty"`
}

// replayReport is the server summary plus the links of the replayed runs.
type replayReport struct {
	*models.ReplayIngestSummary
	Runs []replayRunLink `json:"runs"`
}

// runLinks pairs each run with its Argus link. A dry run gets no link,
// because the run IDs it names do not exist.
func runLinks(base string, runs []models.ReplayRun, dryRun bool) []replayRunLink {
	links := make([]replayRunLink, 0, len(runs))
	for _, r := range runs {
		link := replayRunLink{
			Type:        r.Type,
			ID:          r.ID,
			SourceID:    r.SourceID,
			BuildID:     r.BuildID,
			BuildNumber: r.BuildNumber,
		}
		if !dryRun {
			link.URL = api.RunPageURL(base, r.Type, r.ID)
		}
		links = append(links, link)
	}
	return links
}

// runLine is the text line of one run: the recorded and the new run ID, the
// build, and the link. A dry run names the build that the run would become.
func runLine(r replayRunLink) string {
	build := ""
	if r.BuildID != "" && r.BuildNumber != nil {
		build = fmt.Sprintf(" (%s#%d)", r.BuildID, *r.BuildNumber)
	}
	switch {
	case r.URL == "" && build != "":
		return fmt.Sprintf("Run %s would replay as%s", r.SourceID, build)
	case r.URL == "":
		return ""
	case r.SourceID != "" && r.SourceID != r.ID:
		return fmt.Sprintf("Run %s -> %s%s: %s", r.SourceID, r.ID, build, r.URL)
	default:
		return fmt.Sprintf("Run %s: %s", r.ID, r.URL)
	}
}

// renderReplaySummary writes the report either as JSON (--report json or the
// default JSON output mode) or as a human-readable one-liner, the link of
// each replayed run and, when non-empty, an errors table.
func renderReplaySummary(cmd *cobra.Command, reportFmt string, report replayReport) error {
	summary := report.ReplayIngestSummary

	switch strings.ToLower(reportFmt) {
	case "", "text":
		_, _ = fmt.Fprintf(cmd.OutOrStdout(),
			"Replay summary: total=%d processed=%d succeeded=%d failed=%d skipped=%d backfilled_logs=%d\n",
			summary.Total, summary.Processed, summary.Succeeded, summary.Failed, summary.SkippedNoReplay, summary.BackfilledLogs,
		)
		for _, r := range report.Runs {
			if line := runLine(r); line != "" {
				_, _ = fmt.Fprintln(cmd.OutOrStdout(), line)
			}
		}
		if len(summary.Errors) == 0 {
			return nil
		}
		// Reuse the text outputter for the errors table.
		text := output.New(cmd.OutOrStdout(), true)
		return text.Write(models.NewTabularSlice(summary.Errors))
	case "json":
		return OutputterFrom(cmd.Context()).Write(report)
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
			"When false, submit_run records whose test entity does not yet exist "+
			"are reported as failures naming the would-be release/group/test and which level "+
			"is missing -- rather than silently inserting a broken run with empty test_id. "+
			"Default: on for the local-runs default, off otherwise.")
	replayCmd.Flags().Bool("backfill-logs", true,
		"After replaying, have the server list each run's S3 log prefix and submit links "+
			"for any log archives that were uploaded but whose logs/submit was never recorded "+
			"(e.g. loader/monitor/sct-runner bundles). Uses the server's existing read-only S3 "+
			"credentials; idempotent. On by default; pass --backfill-logs=false to disable. "+
			"Ignored with --dry-run.")
	replayCmd.Flags().String("build-id", "",
		"Replay into a new run under this build path, e.g. scylla-staging/<user>/<job>, optionally ending in #<n> "+
			"to choose the build number (default: the next free one). "+
			"The path names the release, the group and the test, and its last segment is the job name. "+
			"Every replay with --build-id makes a new run, and turns on --as-me. "+
			"Default for one local run: local-runs/<your Argus username>/<first SCT config file>.")
	replayCmd.Flags().String("resume", "",
		"Finish an earlier replay of the same log into the run it made, given by run ID, in place of a new run. "+
			"The run must be the copy of this log's run under the same build path: the same --build-id, "+
			"or the local-runs default when you gave none.")
	replayCmd.Flags().Bool("keep-run", false,
		"Replay a local run as recorded, with its original run ID and path, in place of the local-runs default")
	replayCmd.Flags().Bool("as-me", false,
		"Make your Argus user the assignee and the starter of every new run. Without --build-id, "+
			"only the assignee changes. Default: on for a replay into a build path (--build-id or the local-runs default), off otherwise.")
	replayCmd.Flags().String("target-url", "", "Override the base URL (replay against a different Argus instance)")
	replayCmd.Flags().String("report", "text", `Output format: "text" or "json"`)

	replayCmd.MarkFlagsMutuallyExclusive("dir", "file")
	replayCmd.MarkFlagsMutuallyExclusive("keep-run", "build-id")
	replayCmd.MarkFlagsMutuallyExclusive("keep-run", "resume")

	runCmd.AddCommand(replayCmd)
}
