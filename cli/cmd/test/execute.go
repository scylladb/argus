package test

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

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
		Long: `Trigger a build of a test, addressed by its build_system_id (the Jenkins
job path). Parameters are resolved with the cascade defaults < --file < --param:
the job's current default parameters are the base, a --file JSON map overrides
them, and repeatable --param name=value flags override both.

  # Rebuild with the job's current defaults:
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb

  # Override a couple of values on top of the defaults:
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb \
    --param backend=aws --param region=eu-west-1

  # Start from an edited params file, then tweak one value:
  argus test execute --build-id scylla-2026.2/longevity/longevity-100gb \
    --file params.json --param scylla_version=2026.2

Use --dry-run to print the merged parameters without triggering a build, and
--wait to block until the build leaves the queue and report its URL. If the job
has no builds and no default definitions, the defaults are simply empty and only
your --file/--param values are sent.`,
		RunE: runExecute,
	}

	cmd.Flags().StringP("build-id", "b", "", "Test build_system_id (Jenkins job path) (required)")
	cmd.Flags().Int("build-number", 0, "Seed default parameters from this build number (default: last build)")
	cmd.Flags().StringP("file", "f", "", "JSON file with a {name: value} parameter map (\"-\" for stdin)")
	cmd.Flags().StringArray("param", nil, "Parameter override as name=value (repeatable)")
	cmd.Flags().Bool("dry-run", false, "Print the merged parameters and exit without triggering a build")
	cmd.Flags().Bool("wait", false, "Wait for the build to start and report its URL")
	cmd.Flags().Duration("wait-timeout", 5*time.Minute, "Maximum time to wait when --wait is set")
	_ = cmd.MarkFlagRequired("build-id")

	parent.AddCommand(cmd)
}

// runExecute is the RunE handler for "test execute".
func runExecute(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "test-execute")

	buildID, _ := cmd.Flags().GetString("build-id")
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

	if dryRun {
		log.Info().Str("build_id", buildID).Int("count", len(merged)).Msg("dry run: not triggering build")
		return out.Write(models.NewKVTabular(merged))
	}

	queueItem, err := svc.TriggerBuild(ctx, buildID, merged)
	if err != nil {
		log.Error().Err(err).Str("build_id", buildID).Msg("failed to trigger build")
		return err
	}
	log.Info().Str("build_id", buildID).Int("queue_item", queueItem).Msg("build triggered successfully")

	if !wait {
		return out.Write(models.NewKVTabular(models.JenkinsBuildResponse{QueueItem: queueItem}))
	}

	timeout, _ := cmd.Flags().GetDuration("wait-timeout")
	info, err := svc.WaitForBuild(ctx, queueItem, timeout, 0)
	if err != nil {
		log.Error().Err(err).Int("queue_item", queueItem).Msg("failed while waiting for build to start")
		return err
	}
	log.Info().Str("build_id", buildID).Str("url", info.URL).Msg("build started")
	return out.Write(models.NewKVTabular(info))
}

// loadParamsFile reads the --file parameter map (path or stdin) into a
// {name: value} map. Returns nil when --file is not set.
func loadParamsFile(cmd *cobra.Command) (map[string]any, error) {
	path, _ := cmd.Flags().GetString("file")
	if path == "" {
		return nil, nil
	}

	var raw []byte
	var err error
	if path == "-" {
		raw, err = io.ReadAll(bufio.NewReader(os.Stdin))
	} else {
		raw, err = os.ReadFile(path)
	}
	if err != nil {
		return nil, fmt.Errorf("reading params file: %w", err)
	}

	var params map[string]any
	if err := json.Unmarshal(raw, &params); err != nil {
		return nil, fmt.Errorf("parsing params file (expected a {name: value} object): %w", err)
	}
	return params, nil
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
