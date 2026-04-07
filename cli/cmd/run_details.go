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

// runDetailsCmd fetches the basic summary of a run — the same information
// visible on the Argus "Details" tab — without heavy fields such as logs,
// screenshots, events, nemeses, or allocated cloud resources.
//
// For those fields use the dedicated subcommands:
//   - argus run logs list / download
//   - argus run activity
//   - argus run nemeses
//   - argus run events
//   - argus run results
var runDetailsCmd = &cobra.Command{
	Use:   "details",
	Short: "Show basic details of a test run",
	Long: `Show the basic summary of a test run — the same information visible
on the Argus Details tab — without heavy fields such as logs, screenshots,
events, nemeses, or cloud resources.

For additional information use the dedicated subcommands:
  argus run logs list / download
  argus run activity
  argus run nemeses
  argus run events
  argus run results`,
	RunE: func(cmd *cobra.Command, _ []string) error {
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

		route := fmt.Sprintf(api.TestRunGet, runType, runID)
		req, err := client.NewRequest(ctx, "GET", route, nil)
		if err != nil {
			return err
		}

		switch runType {
		case "scylla-cluster-tests":
			full, err := api.DoJSON[models.SCTTestRun](client, req)
			if err != nil {
				return err
			}
			details := models.SCTRunDetails{
				RunBase:          full.RunBase,
				TestName:         full.TestName,
				ScyllaVersion:    full.ScyllaVersion,
				StartedBy:        full.StartedBy,
				BranchName:       full.BranchName,
				OriginURL:        full.OriginURL,
				ConfigFiles:      full.ConfigFiles,
				ScmRevisionID:    full.ScmRevisionID,
				SubtestName:      full.SubtestName,
				StressDuration:   full.StressDuration,
				YAMLTestDuration: full.YAMLTestDuration,
				RegionName:       full.RegionName,
				Packages:         full.Packages,
			}
			return out.Write(models.NewKVTabular(details))

		case "generic":
			full, err := api.DoJSON[models.GenericRun](client, req)
			if err != nil {
				return err
			}
			details := models.GenericRunDetails{
				RunBase:       full.RunBase,
				StartedBy:     full.StartedBy,
				SubType:       full.SubType,
				ScyllaVersion: full.ScyllaVersion,
			}
			return out.Write(models.NewKVTabular(details))

		case "driver-matrix-tests":
			full, err := api.DoJSON[models.DriverTestRun](client, req)
			if err != nil {
				return err
			}
			details := models.DriverRunDetails{
				RunBase:       full.RunBase,
				ScyllaVersion: full.ScyllaVersion,
			}
			return out.Write(models.NewKVTabular(details))

		case "sirenada":
			full, err := api.DoJSON[models.SirenadaRun](client, req)
			if err != nil {
				return err
			}
			details := models.SirenadaRunDetails{
				RunBase:       full.RunBase,
				ScyllaVersion: full.ScyllaVersion,
				Region:        full.Region,
				SCTTestID:     full.SCTTestID,
			}
			return out.Write(models.NewKVTabular(details))

		default:
			return fmt.Errorf("unknown run type %q, valid types: %s", runType, ValidRunTypes())
		}
	},
}

func init() {
	runDetailsCmd.Flags().String("run-id", "", "Run UUID (required)")
	runDetailsCmd.Flags().String("type", "", "Plugin type (optional, auto-resolved when omitted): "+ValidRunTypes())
	_ = runDetailsCmd.MarkFlagRequired("run-id")

	runCmd.AddCommand(runDetailsCmd)
}
