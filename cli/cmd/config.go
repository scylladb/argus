package cmd

import (
	"fmt"
	"strings"

	"github.com/scylladb/argus/cli/internal/config"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/spf13/cobra"
)

var configCmd = &cobra.Command{
	Use:   "config",
	Short: "View and modify CLI configuration",
	Long: `config provides subcommands to inspect and change the Argus CLI
configuration file (default: $XDG_CONFIG_HOME/argus-cli/config.yaml).

Available subcommands:

  argus config list            — show all settings and their current values
  argus config get <key>       — print the value of a single setting
  argus config set <key> <val> — update a setting and persist it to disk

Recognised keys: ` + strings.Join(config.Keys(), ", "),
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
}

var configListCmd = &cobra.Command{
	Use:         "list",
	Short:       "Show all configuration settings",
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	RunE: func(cmd *cobra.Command, _ []string) error {
		cmd.SilenceUsage = true

		all := config.GetAll(cfgFile)
		keys := config.Keys()
		for _, k := range keys {
			_, _ = fmt.Fprintf(cmd.OutOrStdout(), "%s = %s\n", k, all[k])
		}
		return nil
	},
}

var configGetCmd = &cobra.Command{
	Use:         "get <key>",
	Short:       "Print the value of a configuration setting",
	Args:        cobra.ExactArgs(1),
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	ValidArgsFunction: func(_ *cobra.Command, _ []string, _ string) ([]string, cobra.ShellCompDirective) {
		return config.Keys(), cobra.ShellCompDirectiveNoFileComp
	},
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true

		val, err := config.Get(cfgFile, args[0])
		if err != nil {
			return err
		}
		_, _ = fmt.Fprintln(cmd.OutOrStdout(), val)
		return nil
	},
}

var configSetCmd = &cobra.Command{
	Use:         "set <key> <value>",
	Short:       "Update a configuration setting",
	Args:        cobra.ExactArgs(2),
	Annotations: map[string]string{SkipAuthRetryAnnotation: "true"},
	ValidArgsFunction: func(_ *cobra.Command, args []string, _ string) ([]string, cobra.ShellCompDirective) {
		if len(args) == 0 {
			return config.Keys(), cobra.ShellCompDirectiveNoFileComp
		}
		return nil, cobra.ShellCompDirectiveNoFileComp
	},
	RunE: func(cmd *cobra.Command, args []string) error {
		cmd.SilenceUsage = true
		ctx := cmd.Context()
		log := logging.For(LoggerFrom(ctx), "config")

		key, value := args[0], args[1]
		if err := config.Set(cfgFile, key, value); err != nil {
			return err
		}

		log.Info().Str("key", key).Str("value", value).Msg("config updated")
		_, _ = fmt.Fprintf(cmd.OutOrStdout(), "%s = %s\n", key, value)
		return nil
	},
}

func init() {
	configCmd.AddCommand(configListCmd)
	configCmd.AddCommand(configGetCmd)
	configCmd.AddCommand(configSetCmd)
	rootCmd.AddCommand(configCmd)
}
