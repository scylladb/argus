package test

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerExecute adds the "execute" sub-command to parent.
func registerExecute(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "execute",
		Short: "Trigger a Jenkins test build",
		Long: `Trigger a build of a test. Parameters are resolved with the cascade
defaults < --file < --param: the job's current default parameters are the base,
a --file JSON map overrides them, and repeatable --param name=value flags
override both.

The test is addressed either by its build_system_id directly, or by a release
name plus a test reference resolved against that release's gridview:

  # Rebuild with the job's current defaults (by build_system_id):
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb

  # Same test addressed by release + name:
  argus test execute --release scylla-2026.2 --test longevity/longevity-100gb

  # Override a couple of values on top of the defaults:
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb \
    --param backend=aws --param region=eu-west-1

  # Start from an edited params file, then tweak one value:
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb \
    --file params.json --param scylla_version=2026.2

Use --dry-run to print the merged parameters without triggering a build, and
--wait to block until the build leaves the queue and report its URL. If the job
has no builds and no default definitions, the defaults are simply empty and only
your --file/--param values are sent.

Alternatively, fan out across a plan's labelled tests with --plan-id and one or
more --label flags: every plan test carrying any of the labels is triggered (use
--match-all to require all labels). --param overrides apply to every build;
--wait then blocks until all builds start (or --wait-timeout elapses), waiting in
parallel:

  argus test execute --plan-id scylla-2026.2#3 --label smoke --label nightly
  argus test execute --plan-id scylla-2026.2#3 --label smoke --dry-run
  argus test execute --plan-id scylla-2026.2#3 --label smoke --label perf --match-all --wait`,
		RunE: runExecute,
	}

	addAddressingFlags(cmd)
	cmd.Flags().StringP("plan-id", "p", "", "Plan UUID or key to fan out across (with --label)")
	cmd.Flags().StringArray("label", nil, "Select plan tests carrying this label (repeatable; requires --plan-id)")
	cmd.Flags().Bool("match-all", false, "Require plan tests to carry all --label values instead of any")
	cmd.Flags().Int("build-number", 0, "Seed default parameters from this build number (default: last build)")
	cmd.Flags().StringP("file", "f", "", "JSON file with a {name: value} parameter map (\"-\" for stdin)")
	cmd.Flags().StringArray("param", nil, "Parameter override as name=value (repeatable)")
	cmd.Flags().Bool("dry-run", false, "Print the merged parameters and exit without triggering a build")
	cmd.Flags().Bool("wait", false, "Wait for the build to start and report its URL")
	cmd.Flags().Duration("wait-timeout", 5*time.Minute, "Maximum time to wait when --wait is set")

	// Plan fan-out is its own addressing mode: --plan-id/--label go together and
	// are mutually exclusive with the single-test selectors.
	cmd.MarkFlagsRequiredTogether("plan-id", "label")
	cmd.MarkFlagsMutuallyExclusive("build-id", "plan-id")
	cmd.MarkFlagsMutuallyExclusive("release", "plan-id")
	cmd.MarkFlagsMutuallyExclusive("test", "plan-id")
	cmd.MarkFlagsMutuallyExclusive("build-id", "label")
	cmd.MarkFlagsMutuallyExclusive("release", "label")
	cmd.MarkFlagsMutuallyExclusive("test", "label")

	parent.AddCommand(cmd)
}

// runExecute dispatches to the single-test or plan fan-out path based on whether
// --plan-id was supplied.
func runExecute(cmd *cobra.Command, args []string) error {
	if planID, _ := cmd.Flags().GetString("plan-id"); planID != "" {
		return runExecutePlan(cmd)
	}
	return runExecuteSingle(cmd, args)
}

// runExecuteSingle is the RunE handler for a single-test "test execute".
func runExecuteSingle(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "test-execute")

	buildID, err := resolveBuildID(ctx, cmd, client, c)
	if err != nil {
		return err
	}
	buildNumber := buildNumberFlag(cmd)
	dryRun, _ := cmd.Flags().GetBool("dry-run")
	wait, _ := cmd.Flags().GetBool("wait")

	fileParams, err := loadParamsFile(cmd)
	if err != nil {
		return err
	}
	rawFlags, _ := cmd.Flags().GetStringArray("param")
	flagParams, err := parseParams(rawFlags)
	if err != nil {
		return err
	}

	svc := services.NewTestExecutionService(client, c)

	// Fetch defaults; a job with no builds/defaults is not fatal here — proceed
	// with empty defaults so --file/--param can still launch it.
	defaults, err := svc.FetchParams(ctx, buildID, buildNumber)
	if err != nil {
		if errors.Is(err, services.ErrNoBuildsAvailable) {
			log.Warn().Str("build_id", buildID).Msg("no builds available; sending empty defaults plus --file/--param values")
			defaults = nil
		} else {
			log.Error().Err(err).Str("build_id", buildID).Msg("failed to fetch default parameters")
			return err
		}
	}

	merged := services.MergeParams(defaults, fileParams, flagParams)
	normalizeSCTVersionSource(merged, explicitParamKeys(fileParams, flagParams))

	if dryRun {
		log.Info().Str("build_id", buildID).Int("count", len(merged)).Msg("dry run: not triggering build")
		return out.Write(models.NewKVTabular(merged))
	}

	queueItem, nextBuildNumber, err := svc.TriggerBuildWithNumber(ctx, buildID, merged)
	if err != nil {
		log.Error().Err(err).Str("build_id", buildID).Msg("failed to trigger build")
		return err
	}
	log.Info().Str("build_id", buildID).Int("queue_item", queueItem).Msg("build triggered successfully")

	if !wait {
		cfg := cmdctx.ConfigFrom(ctx)
		result := models.ExecutedBuild{
			BuildID:     buildID,
			QueueItem:   queueItem,
			BuildNumber: nextBuildNumber,
			ArgusURL:    argusRunURL(cfg.URL, buildID, nextBuildNumber),
		}
		log.Info().Str("build_id", buildID).Int("build_number", nextBuildNumber).Str("argus_url", result.ArgusURL).Msg("build queued")
		return out.Write(models.NewKVTabular(result))
	}

	timeout, _ := cmd.Flags().GetDuration("wait-timeout")
	info, err := svc.WaitForBuild(ctx, queueItem, timeout, 0)
	if err != nil {
		log.Error().Err(err).Int("queue_item", queueItem).Msg("failed while waiting for build to start")
		return err
	}
	cfg := cmdctx.ConfigFrom(ctx)
	result := models.StartedBuild{
		BuildID:     buildID,
		JenkinsURL:  info.URL,
		BuildNumber: info.Number,
		ArgusURL:    argusRunURL(cfg.URL, buildID, info.Number),
	}
	log.Info().Str("build_id", buildID).Str("url", info.URL).Str("argus_url", result.ArgusURL).Msg("build started")
	return out.Write(models.NewKVTabular(result))
}

// runExecutePlan is the RunE handler for the plan fan-out mode of "test execute"
// (--plan-id with --label): it resolves the plan's labelled tests and triggers a
// build for each, optionally waiting for all of them in parallel.
func runExecutePlan(cmd *cobra.Command) error {
	cmd.SilenceUsage = true

	// --file and --build-number are per-test and make no sense across a fan-out;
	// reject them up front (before any dependencies are touched).
	if path, _ := cmd.Flags().GetString("file"); path != "" {
		return fmt.Errorf("--file is not supported with --plan-id (each test has its own parameters)")
	}
	if cmd.Flags().Changed("build-number") {
		return fmt.Errorf("--build-number is not supported with --plan-id (each test is a distinct job)")
	}

	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "test-execute-plan")

	planID, _ := cmd.Flags().GetString("plan-id")
	labels, _ := cmd.Flags().GetStringArray("label")
	matchAll, _ := cmd.Flags().GetBool("match-all")
	dryRun, _ := cmd.Flags().GetBool("dry-run")
	wait, _ := cmd.Flags().GetBool("wait")

	rawFlags, _ := cmd.Flags().GetStringArray("param")
	flagParams, err := parseParams(rawFlags)
	if err != nil {
		return err
	}

	planner := services.NewPlannerService(client, c)
	targets, err := planner.ResolveLabeledTests(ctx, planID, labels, matchAll)
	if err != nil {
		log.Error().Err(err).Str("plan_id", planID).Msg("failed to resolve labelled tests")
		return err
	}
	log.Info().Str("plan_id", planID).Int("count", len(targets)).Bool("match_all", matchAll).Msg("resolved labelled tests")

	if dryRun {
		overview := make(models.ReleaseGrid, len(targets))
		for _, t := range targets {
			overview[t.Ref] = t.BuildSystemID
		}
		log.Info().Str("plan_id", planID).Int("count", len(targets)).Msg("dry run: not triggering builds")
		return out.Write(overview)
	}

	svc := services.NewTestExecutionService(client, c)

	// Trigger sequentially so queue assignment is deterministic; a per-test
	// failure is recorded and the batch continues.
	results := make(models.TriggeredBuilds, len(targets))
	for i, t := range targets {
		results[i] = models.TriggeredBuild{Test: t.Ref, BuildSystemID: t.BuildSystemID}

		defaults, err := svc.FetchParams(ctx, t.BuildSystemID, nil)
		if err != nil {
			if errors.Is(err, services.ErrNoBuildsAvailable) {
				log.Warn().Str("build_id", t.BuildSystemID).Msg("no builds available; sending only --param values")
				defaults = nil
			} else {
				log.Error().Err(err).Str("build_id", t.BuildSystemID).Msg("failed to fetch default parameters")
				results[i].Status = "error: " + err.Error()
				continue
			}
		}

		merged := services.MergeParams(defaults, nil, flagParams)
		normalizeSCTVersionSource(merged, explicitParamKeys(flagParams))
		queueItem, err := svc.TriggerBuild(ctx, t.BuildSystemID, merged)
		if err != nil {
			// A validation failure is terminal (the request can never succeed
			// as-is) and usually stems from --param overrides shared across the
			// whole fan-out, so the remaining tests would fail identically.
			// Abort immediately instead of triggering more doomed builds.
			if services.IsValidationError(err) {
				log.Error().Err(err).Str("build_id", t.BuildSystemID).Msg("build request failed validation; aborting remaining builds")
				return fmt.Errorf("aborting plan execution: %s failed validation: %w", t.BuildSystemID, err)
			}
			log.Error().Err(err).Str("build_id", t.BuildSystemID).Msg("failed to trigger build")
			results[i].Status = "error: " + err.Error()
			continue
		}
		results[i].QueueItem = queueItem
		results[i].Status = "queued"
		log.Info().Str("build_id", t.BuildSystemID).Int("queue_item", queueItem).Msg("build triggered")
	}

	if wait {
		timeout, _ := cmd.Flags().GetDuration("wait-timeout")
		cfg := cmdctx.ConfigFrom(ctx)
		waitAllBuilds(ctx, svc, results, cfg.URL, timeout, log)
	}

	return out.Write(results)
}

// waitAllBuilds waits, in parallel, for every successfully-queued build in
// results to leave the queue and receive an executable URL. A single
// batch-wide deadline (timeout) bounds the whole wait; when it elapses the
// shared context is cancelled and any still-pending builds are marked timed out.
// results is mutated in place — each goroutine writes only its own index.
// argusBase is the Argus base URL used to derive each row's Argus run link once
// its build number is known.
func waitAllBuilds(ctx context.Context, svc *services.TestExecutionService, results models.TriggeredBuilds, argusBase string, timeout time.Duration, log zerolog.Logger) {
	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	var wg sync.WaitGroup
	for i := range results {
		if results[i].QueueItem == 0 {
			continue // skipped or failed to trigger — nothing to wait for.
		}
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			info, err := svc.WaitForBuild(waitCtx, results[i].QueueItem, timeout, 0)
			if err != nil {
				if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
					results[i].Status = "timed out"
				} else {
					results[i].Status = "error: " + err.Error()
				}
				return
			}
			results[i].URL = info.URL
			results[i].ArgusURL = argusRunURL(argusBase, results[i].BuildSystemID, info.Number)
			results[i].Status = "started"
		}(i)
	}
	wg.Wait()
	log.Info().Int("count", len(results)).Msg("finished waiting for builds")
}

// loadParamsFile reads the --file parameter map (path or stdin) into a
// {name: value} map. Returns nil when --file is not set.
func loadParamsFile(cmd *cobra.Command) (map[string]any, error) {
	path, _ := cmd.Flags().GetString("file")
	if path == "" {
		return nil, nil
	}

	raw, err := readFileOrStdin(path)
	if err != nil {
		return nil, fmt.Errorf("reading params file: %w", err)
	}

	var params map[string]any
	if err := json.Unmarshal(raw, &params); err != nil {
		return nil, fmt.Errorf("parsing params file (expected a {name: value} object): %w", err)
	}
	return params, nil
}

// argusRunURL builds the stable Argus run link for a build from the configured
// Argus base URL, the test's build_system_id, and its Jenkins build number.
// It returns "" when the build number is not yet known (number == 0).
func argusRunURL(base, buildID string, number int) string {
	if number == 0 {
		return ""
	}
	return strings.TrimRight(base, "/") + "/test/" + buildID + "/" + strconv.Itoa(number)
}

// sctVersionSourceFamilies mirrors the backend SCT_VERSION_SOURCE_FAMILIES: each
// family maps to the parameter keys that *select* it. A scylla-cluster-tests
// build must set exactly one family, otherwise the backend rejects it. Keep this
// in sync with argus/backend/service/jenkins_service.py.
var sctVersionSourceFamilies = map[string][]string{
	"scylla_version":  {"scylla_version"},
	"scylla_repo":     {"scylla_repo"},
	"scylla_image":    {"scylla_ami_id", "gce_image_db", "azure_image_db", "oci_image_db"},
	"rolling_upgrade": {"new_scylla_repo"},
	"scylla_byo":      {"byo_scylla_repo"},
}

// sctFamilyCompanionKeys lists non-selecting parameters that belong to a family
// and must be cleared alongside it (e.g. the BYO branch that only makes sense
// paired with a BYO repo).
var sctFamilyCompanionKeys = map[string][]string{
	"scylla_byo": {"byo_scylla_branch"},
}

// normalizeSCTVersionSource resolves Scylla version-source collisions before a
// scylla-cluster-tests build is triggered. Job defaults frequently seed several
// version-source keys at once (e.g. a default scylla_version alongside a
// scylla_repo), which the backend rejects as ambiguous. When the caller
// *explicitly* selects exactly one source family (via --file/--param, tracked in
// explicit), the sibling families' keys present in merged are cleared to "" so
// only the chosen source survives. Keys are emptied rather than deleted so
// Jenkins cannot reintroduce its own default and recreate the collision.
//
// When zero or several families are explicitly selected, merged is left
// untouched and the backend validator has the final say.
func normalizeSCTVersionSource(merged map[string]any, explicit map[string]struct{}) {
	var chosen string
	families := 0
	for family, keys := range sctVersionSourceFamilies {
		if anyKeyExplicit(explicit, keys) {
			families++
			chosen = family
		}
	}
	if families != 1 {
		return
	}
	for family, keys := range sctVersionSourceFamilies {
		if family == chosen {
			continue
		}
		clearPresent(merged, keys)
		clearPresent(merged, sctFamilyCompanionKeys[family])
	}
}

// anyKeyExplicit reports whether any of keys was explicitly provided by the
// caller.
func anyKeyExplicit(explicit map[string]struct{}, keys []string) bool {
	for _, key := range keys {
		if _, ok := explicit[key]; ok {
			return true
		}
	}
	return false
}

// clearPresent empties (to "") the given keys that already exist in merged,
// leaving absent keys absent so no spurious parameters are added to the build.
func clearPresent(merged map[string]any, keys []string) {
	for _, key := range keys {
		if _, ok := merged[key]; ok {
			merged[key] = ""
		}
	}
}

// explicitParamKeys returns the set of parameter names the caller explicitly
// provided across the given maps (--file and --param). It distinguishes the
// version source the user actually chose from values merely inherited from job
// defaults.
func explicitParamKeys(maps ...map[string]any) map[string]struct{} {
	keys := make(map[string]struct{})
	for _, m := range maps {
		for k := range m {
			keys[k] = struct{}{}
		}
	}
	return keys
}

// readFileOrStdin returns the contents of the file at path, or of standard
// input when path is "-".
func readFileOrStdin(path string) ([]byte, error) {
	if path == "-" {
		return io.ReadAll(bufio.NewReader(os.Stdin))
	}
	return os.ReadFile(path)
}

// parseParams parses repeatable "name=value" flag values into a parameter map.
// The first "=" separates the name from the value; the value may be empty and
// may itself contain "=".
func parseParams(raw []string) (map[string]any, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	out := make(map[string]any, len(raw))
	for _, p := range raw {
		name, value, ok := strings.Cut(p, "=")
		name = strings.TrimSpace(name)
		if !ok || name == "" {
			return nil, fmt.Errorf("invalid --param %q: expected name=value", p)
		}
		out[name] = value
	}
	return out, nil
}
