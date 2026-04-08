package cmd

import (
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
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

		runID, _ := cmd.Flags().GetString("run-id")
		runType, _ := cmd.Flags().GetString("type")

		// Auto-resolve run type when --type is not provided.
		if runType == "" {
			typeKey := cache.RunTypeKey(runID)
			if cached, _, err := cache.Get[models.RunType](c, typeKey); isCacheable(err) {
				runType = cached.RunType
			} else {
				var resolveErr error
				runType, resolveErr = ResolveRunType(ctx, client, runID)
				if resolveErr != nil {
					return resolveErr
				}
				_ = cache.Set(c, typeKey, models.RunType{RunType: runType}, fmt.Sprintf(api.TestRunGetType, runID), cache.TTLRunType)
			}
		}

		handler, ok := RunTypeHandlers[runType]
		if !ok {
			return fmt.Errorf("unknown run type %q, valid types: %s", runType, ValidRunTypes())
		}

		cacheKey := cache.RunKey(runType, runID)

		if getter, ok := runTypeCacheGetters[runType]; ok {
			if cached, err := getter(c, cacheKey); isCacheable(err) {
				return out.Write(models.NewKVTabular(cached))
			}
		}

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}
		result, err := handler(client, req)
		if err != nil {
			return err
		}
		if setter, ok := runTypeCacheSetters[runType]; ok {
			_ = setter(c, cacheKey, result)
		}

		return out.Write(models.NewKVTabular(result))
	},
}

func init() {
	runDetailsCmd.Flags().String("run-id", "", "Run UUID (required)")
	runDetailsCmd.Flags().String("type", "", "Plugin type (optional, auto-resolved when omitted): "+ValidRunTypes())
	_ = runDetailsCmd.MarkFlagRequired("run-id")

	runCmd.AddCommand(runDetailsCmd)
}
