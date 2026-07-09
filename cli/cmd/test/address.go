package test

import (
	"context"
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// addFlags registers the shared test-addressing flags on cmd: either an
// explicit --build-id, or a --release + --test pair resolved against the
// release's gridview. The two modes are mutually exclusive; --release and
// --test must be supplied together.
func addAddressingFlags(cmd *cobra.Command) {
	cmd.Flags().StringP("build-id", "b", "", "Test build_system_id (Jenkins job path)")
	cmd.Flags().StringP("release", "r", "", "Release name to resolve --test against (e.g. scylla-2026.2)")
	cmd.Flags().StringP("test", "t", "", "Test reference within --release (build_system_id, group/test, or name)")
	cmd.MarkFlagsMutuallyExclusive("build-id", "test")
	cmd.MarkFlagsMutuallyExclusive("build-id", "release")
	cmd.MarkFlagsRequiredTogether("release", "test")
}

// resolveBuildID determines the target test's build_system_id from the
// addressing flags. --build-id is returned verbatim (no network call); a
// --release + --test pair is resolved to a build_system_id via the planner
// gridview. Exactly one addressing mode must be supplied.
func resolveBuildID(ctx context.Context, cmd *cobra.Command, client *api.Client, c *cache.Cache) (string, error) {
	buildID, _ := cmd.Flags().GetString("build-id")
	release, _ := cmd.Flags().GetString("release")
	test, _ := cmd.Flags().GetString("test")

	if buildID != "" {
		return buildID, nil
	}
	if release == "" || test == "" {
		return "", fmt.Errorf("a test must be addressed with either --build-id or --release together with --test")
	}

	svc := services.NewPlannerService(client, c)
	return svc.ResolveTestBuildID(ctx, release, test)
}
