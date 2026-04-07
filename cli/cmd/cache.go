package cmd

import (
	"fmt"
	"io"

	"github.com/spf13/cobra"
)

var cacheCmd = &cobra.Command{
	Use:   "cache",
	Short: "Manage the local response cache",
	Long: `Inspect and manage the file-based response cache used to avoid
redundant network calls to the Argus API.

Cached responses are stored as plain JSON files under the application's XDG
cache directory, organised by resource type so you can browse them directly:

  ~/.cache/argus-cli/cache/
  ├── runs/scylla-cluster-tests/<run-id>/data.json
  ├── activity/<run-id>/data.json
  ├── comments/run/<run-id>/data.json
  └── …`,
}

var cacheClearCmd = &cobra.Command{
	Use:   "clear",
	Short: "Delete all cached responses",
	Long:  `Remove every entry from the local cache. The next command invocation will fetch fresh data from the API.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		c := CacheFrom(cmd.Context())
		if err := c.Clear(); err != nil {
			return err
		}
		_, err := fmt.Fprintln(cmd.OutOrStdout(), "cache cleared")
		return err
	},
}

var cacheInfoCmd = &cobra.Command{
	Use:   "info",
	Short: "Show cache location and statistics",
	Long:  `Display the cache directory path, total disk usage, entry count, and a per-category breakdown.`,
	RunE: func(cmd *cobra.Command, _ []string) error {
		c := CacheFrom(cmd.Context())

		stats, err := c.Stats()
		if err != nil {
			return err
		}

		w := cmd.OutOrStdout()
		if err := fprintfAll(w,
			fmt.Sprintf("Directory : %s\n", stats.Dir),
			fmt.Sprintf("Entries   : %d (%d expired)\n", stats.Entries, stats.Expired),
			fmt.Sprintf("Size      : %s\n", formatBytes(stats.TotalBytes)),
		); err != nil {
			return err
		}

		if len(stats.Categories) > 0 {
			if err := fprintfAll(w,
				"\n",
				"Category             Entries  Expired  Size\n",
				"--------------------  -------  -------  ----\n",
			); err != nil {
				return err
			}
			for name, cat := range stats.Categories {
				if _, err := fmt.Fprintf(w, "%-20s  %7d  %7d  %s\n",
					name, cat.Entries, cat.Expired, formatBytes(cat.Bytes)); err != nil {
					return err
				}
			}
		}

		return nil
	},
}

// fprintfAll writes each string in lines to w, returning on the first error.
func fprintfAll(w io.Writer, lines ...string) error {
	for _, line := range lines {
		if _, err := io.WriteString(w, line); err != nil {
			return err
		}
	}
	return nil
}

func init() {
	cacheCmd.AddCommand(cacheClearCmd, cacheInfoCmd)
	rootCmd.AddCommand(cacheCmd)
}

// formatBytes converts a byte count into a human-readable string.
func formatBytes(n int64) string {
	const (
		_  = iota
		KB = 1 << (10 * iota)
		MB
		GB
	)
	switch {
	case n >= GB:
		return fmt.Sprintf("%.1f GB", float64(n)/GB)
	case n >= MB:
		return fmt.Sprintf("%.1f MB", float64(n)/MB)
	case n >= KB:
		return fmt.Sprintf("%.1f KB", float64(n)/KB)
	default:
		return fmt.Sprintf("%d B", n)
	}
}
