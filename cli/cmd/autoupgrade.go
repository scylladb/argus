package cmd

import (
	"context"
	"io"
	"os"

	"github.com/spf13/cobra"

	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/selfupdate"
)

const (
	// envNoAutoUpgrade turns the daily check off. argus upgrade still works.
	envNoAutoUpgrade = "ARGUS_NO_AUTO_UPGRADE"
	// EnvUpgradedFrom holds the version that exec replaced. The new process skips the daily check.
	EnvUpgradedFrom = "ARGUS_UPGRADED_FROM"
)

type dailyUpdater interface {
	Daily(ctx context.Context, stderr io.Writer) (selfupdate.Result, error)
}

// newDailyUpdater builds the updater of the daily check. Tests replace it.
var newDailyUpdater = func(version string) dailyUpdater {
	return selfupdate.New(version, selfupdate.WithStateDir(config.CacheDir()))
}

// skipsAutoUpgrade reports whether the command line runs a command that must not start the
// daily check: the upgrade command, the version command, help, and the shell completion
// commands. The version command reports the installed binary, so a deployment can read it in
// a dry run.
func skipsAutoUpgrade(args []string) bool {
	for _, arg := range args[1:] {
		switch arg {
		case "--":
			// The arguments after "--" are values, not commands or flags.
			return isReadOnlyTarget(args)
		case cobra.ShellCompRequestCmd, cobra.ShellCompNoDescRequestCmd, "-h", "--help":
			// Cobra adds the completion request commands only when it executes, so Find does
			// not know them. They can follow persistent flags.
			return true
		}
	}
	return isReadOnlyTarget(args)
}

// isReadOnlyTarget reports whether the command of args is the root, help, version, upgrade or
// completion command.
func isReadOnlyTarget(args []string) bool {
	// Cobra adds the help and completion commands when it executes. Add them now so Find
	// knows them.
	rootCmd.InitDefaultHelpCmd()
	rootCmd.InitDefaultCompletionCmd()
	target, _, err := rootCmd.Find(args[1:])
	if err != nil {
		return false
	}
	if target == rootCmd || target == upgradeCmd || target == cliVersionCmd {
		return true
	}
	for c := target; c != nil && c != rootCmd; c = c.Parent() {
		if c.Name() == "help" || c.Name() == "completion" {
			return true
		}
	}
	return false
}

// AutoUpgrade runs the daily update check before the command of args runs. It returns the
// path of the new binary and true when the check installed a newer release. The caller then
// replaces its process with that binary.
func AutoUpgrade(ctx context.Context, args []string, stderr io.Writer) (string, bool) {
	version := buildVersion.version
	if selfupdate.IsDev(version) || envBoolTrue(envNoAutoUpgrade) || os.Getenv(EnvUpgradedFrom) != "" ||
		skipsAutoUpgrade(args) {
		return "", false
	}
	res, err := newDailyUpdater(version).Daily(ctx, stderr)
	if err != nil || !res.Upgraded {
		return "", false
	}
	return res.Path, true
}
