package cmd

import (
	"context"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"

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
	// Cobra adds the help and completion commands when it executes. Add them now so Find
	// knows them.
	rootCmd.InitDefaultHelpCmd()
	rootCmd.InitDefaultCompletionCmd()
	target, _, err := rootCmd.Find(args[1:])
	if err != nil {
		target = nil
	}
	for _, arg := range args[1:] {
		switch {
		case arg == "--":
			// The arguments after "--" are values, not commands or flags.
			return isReadOnlyTarget(target)
		case arg == cobra.ShellCompRequestCmd || arg == cobra.ShellCompNoDescRequestCmd:
			// Cobra adds the completion request commands only when it executes, so Find does
			// not know them. They can follow persistent flags.
			return true
		case asksForHelp(target, arg):
			return true
		}
	}
	return isReadOnlyTarget(target)
}

// isReadOnlyTarget reports whether target is the root, help, version, upgrade or completion
// command. A nil target is a command line that Cobra cannot resolve.
func isReadOnlyTarget(target *cobra.Command) bool {
	if target == nil {
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

// asksForHelp reports whether arg sets the help flag of target in a form that pflag accepts:
// --help, --help=<true>, -h, -h=<true>, or h among combined short flags, as in -vh. A nil
// target resolves short flags against the root command.
func asksForHelp(target *cobra.Command, arg string) bool {
	if long, ok := strings.CutPrefix(arg, "--"); ok {
		name, value, hasValue := strings.Cut(long, "=")
		return name == "help" && (!hasValue || isTrue(value))
	}
	shorts, ok := strings.CutPrefix(arg, "-")
	if !ok {
		return false
	}
	if target == nil {
		target = rootCmd
	}
	for i, c := range shorts {
		f := shorthandFlag(target, string(c))
		if c == 'h' && (f == nil || f.Name == "help") {
			value, hasValue := strings.CutPrefix(shorts[i+1:], "=")
			return !hasValue || isTrue(value)
		}
		// pflag reads the rest of the argument as the value of a flag that takes one.
		if f == nil || f.NoOptDefVal == "" {
			return false
		}
	}
	return false
}

// shorthandFlag returns the flag of target or of its parents with the shorthand name.
func shorthandFlag(target *cobra.Command, name string) *pflag.Flag {
	if f := target.Flags().ShorthandLookup(name); f != nil {
		return f
	}
	return target.InheritedFlags().ShorthandLookup(name)
}

func isTrue(value string) bool {
	b, err := strconv.ParseBool(value)
	return err == nil && b
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
