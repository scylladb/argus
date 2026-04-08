package cmd

import (
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
)

// ---------------------------------------------------------------------------
// Subcommand: run details
// ---------------------------------------------------------------------------

// runDetailsCmd fetches the full details of a test run, including all fields
// such as logs, screenshots, events, nemeses, and allocated cloud resources.
var runDetailsCmd = &cobra.Command{
	Use:   "details",
	Short: "Get full details of a test run",
	Long: `Fetch the full details of a test run by its run ID.

When --type is omitted the plugin type is resolved automatically via the
/run/<run_id>/type endpoint and cached for 24 h so subsequent invocations
require no network round-trip for type resolution.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		client := APIClientFrom(ctx)
		out := OutputterFrom(ctx)
		c := CacheFrom(ctx)
		log := logging.For(LoggerFrom(ctx), "run-details")

		runID, _ := cmd.Flags().GetString("run-id")
		runType, _ := cmd.Flags().GetString("type")

		log.Debug().Str("run_id", runID).Str("type_flag", runType).Msg("fetching run details")

		// Auto-resolve run type when --type is not provided.
		if runType == "" {
			typeKey := cache.RunTypeKey(runID)
			if cached, _, err := cache.Get[models.RunType](c, typeKey); isCacheable(err) {
				runType = cached.RunType
				log.Debug().Str("run_id", runID).Str("run_type", runType).Msg("run type resolved from cache")
			} else {
				log.Debug().Str("run_id", runID).Msg("resolving run type from API")
				var resolveErr error
				runType, resolveErr = ResolveRunType(ctx, client, runID)
				if resolveErr != nil {
					log.Error().Err(resolveErr).Str("run_id", runID).Msg("failed to resolve run type")
					return resolveErr
				}
				log.Debug().Str("run_id", runID).Str("run_type", runType).Msg("run type resolved from API")
				_ = cache.Set(c, typeKey, models.RunType{RunType: runType}, fmt.Sprintf(api.TestRunGetType, runID), cache.TTLRunType)
			}
		}

		handler, ok := RunTypeHandlers[runType]
		if !ok {
			err := fmt.Errorf("unknown run type %q, valid types: %s", runType, ValidRunTypes())
			log.Error().Err(err).Str("run_type", runType).Msg("unsupported run type")
			return err
		}

		cacheKey := cache.RunKey(runType, runID)

		if getter, ok := runTypeCacheGetters[runType]; ok {
			if cached, err := getter(c, cacheKey); isCacheable(err) {
				log.Debug().Str("run_id", runID).Str("run_type", runType).Msg("run details served from cache")
				return out.Write(models.NewKVTabular(cached))
			}
		}

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		log.Debug().Str("run_id", runID).Str("run_type", runType).Str("route", route).Msg("fetching run details from API")
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("route", route).Msg("failed to build request")
			return err
		}
		result, err := handler(client, req)
		if err != nil {
			log.Error().Err(err).Str("run_id", runID).Str("run_type", runType).Msg("API request for run details failed")
			return err
		}
		if setter, ok := runTypeCacheSetters[runType]; ok {
			if cacheErr := setter(c, cacheKey, result); cacheErr != nil {
				log.Warn().Err(cacheErr).Str("run_id", runID).Msg("failed to cache run details")
			}
		}

		log.Info().Str("run_id", runID).Str("run_type", runType).Msg("run details fetched successfully")
		return out.Write(models.NewKVTabular(result))
	},
}

func init() {
	runDetailsCmd.Flags().String("run-id", "", "Run UUID (required)")
	runDetailsCmd.Flags().String("type", "", "Plugin type (optional, auto-resolved when omitted): "+ValidRunTypes())
	_ = runDetailsCmd.MarkFlagRequired("run-id")

	runCmd.AddCommand(runDetailsCmd)
}
