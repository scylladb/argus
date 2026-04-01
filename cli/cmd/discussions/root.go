// Package discussions provides the "comment submit", "comment update", and
// "comment delete" cobra sub-commands.  It is wired into the command tree by
// the parent cmd package via [Register].
package discussions

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// RunFetcher is set by the parent cmd package at init time.  It provides the
// run-type resolution and typed fetch machinery needed by [services.DiscussionService]
// to resolve test IDs from runs.
var RunFetcher services.RunFetcher

// Register adds the discussion write sub-commands (submit, update, delete)
// to the given parent command.  The parent is typically the "comment" command
// owned by the cmd package.
func Register(parent *cobra.Command) {
	registerSubmit(parent)
	registerUpdate(parent)
	registerDelete(parent)
}

// readMessage returns the message from the --message flag, or reads from stdin
// when the flag is empty.  This allows piping content into submit/update.
func readMessage(cmd *cobra.Command) (string, error) {
	msg, _ := cmd.Flags().GetString("message")
	if msg != "" {
		return msg, nil
	}

	info, err := os.Stdin.Stat()
	if err != nil {
		return "", fmt.Errorf("checking stdin: %w", err)
	}
	if info.Mode()&os.ModeCharDevice != 0 {
		return "", fmt.Errorf("--message is required (or pipe content via stdin)")
	}

	scanner := bufio.NewScanner(os.Stdin)
	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return "", fmt.Errorf("reading stdin: %w", err)
	}
	result := strings.Join(lines, "\n")
	if result == "" {
		return "", fmt.Errorf("--message is required (stdin was empty)")
	}
	return result, nil
}

// ParseMentions splits a comma-separated --mention flag into a slice of
// user-ID strings.  Returns nil when the flag is empty.
func ParseMentions(cmd *cobra.Command) []string {
	raw, _ := cmd.Flags().GetString("mention")
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if t := strings.TrimSpace(p); t != "" {
			out = append(out, t)
		}
	}
	return out
}
