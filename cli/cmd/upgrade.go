package cmd

import (
	"context"
	"fmt"

	"github.com/spf13/cobra"

	"github.com/scylladb/argus/cli/internal/output"
	"github.com/scylladb/argus/cli/internal/selfupdate"
)

type upgrader interface {
	Upgrade(ctx context.Context, allowPrerelease bool) (selfupdate.Result, error)
}

// newUpgrader builds the updater of the upgrade command. Tests replace it.
var newUpgrader = func(version string) upgrader { return selfupdate.New(version) }

var upgradeCmd = &cobra.Command{
	Use:   "upgrade",
	Short: "Install the newest argus CLI release over this binary",
	Long: `Install the newest argus CLI release from GitHub over this binary.

The command installs a stable release. On a pre-release build it also installs
a newer pre-release of the same version. --prerelease installs the newest
release of any kind. A dev build does not upgrade.`,
	Args:        cobra.NoArgs,
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	// The upgrade needs no config, no API client and no Cloudflare token.
	PersistentPreRunE: func(_ *cobra.Command, _ []string) error { return nil },
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		prerelease, err := cmd.Flags().GetBool("prerelease")
		if err != nil {
			return err
		}

		res, err := newUpgrader(buildVersion.version).Upgrade(cmd.Context(), prerelease)
		if err != nil {
			return err
		}

		if !useText {
			return output.New(cmd.OutOrStdout(), false).Write(res)
		}
		if res.Upgraded {
			_, err = fmt.Fprintf(cmd.OutOrStdout(), "argus upgraded %s -> %s\n", res.From, res.To)
		} else {
			_, err = fmt.Fprintf(cmd.OutOrStdout(), "argus %s is the newest release\n", res.To)
		}
		return err
	},
}

func init() {
	upgradeCmd.Flags().Bool("prerelease", false, "also install pre-releases")
	rootCmd.AddCommand(upgradeCmd)
}
