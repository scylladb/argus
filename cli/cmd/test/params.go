package test

import (
	"errors"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// registerParams adds the "params" sub-command to parent.
func registerParams(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "params",
		Short: "Show a Jenkins job's parameters",
		Long: `Fetch the parameter set for a test. By default the last build's
values are used, falling back to the job's default parameter definitions.

The test is addressed either by its build_system_id directly, or by a release
name plus a test reference resolved against that release's gridview:
  argus test params --build-id scylla-2026.2/longevity/longevity-100gb
  argus test params --release scylla-2026.2 --test longevity/longevity-100gb

By default only a {name: value} map is emitted, which can be redirected to a
file and fed straight into 'test execute --file':
  argus test params --build-id scylla-2026.2/longevity/longevity-100gb > params.json

Use --full to also see each parameter's description and allowed choices. If the
job has no builds and no default definitions, this command fails; use
'test execute' with --file/--param to launch it anyway.`,
		RunE: runParams,
	}

	addAddressingFlags(cmd)
	cmd.Flags().Int("build-number", 0, "Seed parameters from this build number (default: last build)")
	cmd.Flags().Bool("full", false, "Show full parameter details (description, choices) instead of a values map")

	parent.AddCommand(cmd)
}

// runParams is the RunE handler for "test params".
func runParams(cmd *cobra.Command, _ []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "test-params")

	buildID, err := resolveBuildID(ctx, cmd, client, c)
	if err != nil {
		return err
	}
	buildNumber := buildNumberFlag(cmd)
	full, _ := cmd.Flags().GetBool("full")
	log.Debug().Str("build_id", buildID).Bool("full", full).Msg("fetching job parameters")

	svc := services.NewTestExecutionService(client, c)

	params, err := svc.FetchParams(ctx, buildID, buildNumber)
	if err != nil {
		if errors.Is(err, services.ErrNoBuildsAvailable) {
			log.Error().Str("build_id", buildID).Msg("no builds available; job default parameters unavailable")
		} else {
			log.Error().Err(err).Str("build_id", buildID).Msg("failed to fetch job parameters")
		}
		return err
	}

	log.Info().Str("build_id", buildID).Int("count", len(params)).Msg("job parameters fetched successfully")

	if full {
		return out.Write(models.NewParamsTable(params))
	}

	values := make(map[string]any, len(params))
	for _, p := range params {
		values[p.Name] = p.Value
	}
	return out.Write(models.NewKVTabular(values))
}

// buildNumberFlag returns a pointer to the --build-number value, or nil when the
// flag was not set (so the backend seeds from the last build).
func buildNumberFlag(cmd *cobra.Command) *int {
	if !cmd.Flags().Changed("build-number") {
		return nil
	}
	n, _ := cmd.Flags().GetInt("build-number")
	return &n
}
