package cmd

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/scylladb/argus/cli/internal/api"
)

// buildVersion holds the version metadata injected by main via SetVersionInfo.
var buildVersion = struct {
	version string
	commit  string
	date    string
}{
	version: "dev",
	commit:  "none",
	date:    "unknown",
}

// SetVersionInfo is called by main to forward the ldflags-injected build
// metadata into the cmd package before ExecuteContext is invoked. The
// version also goes into the User-Agent header of every Argus request.
func SetVersionInfo(version, commit, date string) {
	buildVersion.version = version
	buildVersion.commit = commit
	buildVersion.date = date
	api.SetVersion(version)
}

var cliVersionCmd = &cobra.Command{
	Use:         "version",
	Short:       "Print the version and build information",
	Long:        `Display the version, commit SHA, and build date of this argus binary.`,
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	// Override PersistentPreRunE so the root setup (config load, API client,
	// CF auth) is skipped — the version command needs none of that.
	PersistentPreRunE: func(_ *cobra.Command, _ []string) error { return nil },
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true
		_, err := fmt.Fprintf(cmd.OutOrStdout(),
			"argus %s (commit: %s, built: %s)\n",
			buildVersion.version,
			buildVersion.commit,
			buildVersion.date,
		)
		return err
	},
}

func init() {
	rootCmd.AddCommand(cliVersionCmd)
}
