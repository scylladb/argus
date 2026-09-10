package cmd

import (
	"github.com/scylladb/argus/cli/cmd/myjobs"
	"github.com/spf13/cobra"
)

// myJobsCmd is the parent command for a user's job overview.
var myJobsCmd = &cobra.Command{
	Use:   "my-jobs",
	Short: "Show the jobs assigned to you (or another user)",
	Long: `Show the runs assigned to a user and the tests they are planned to execute,
mirroring the "My Jobs" profile page.

Without a sub-command the assigned runs are listed, filtered by
--status / --investigation-status. When a filter flag is not given it defaults
to: status is anything but "passed", investigation status is "not_investigated"
or "in_progress" - i.e. what still needs attention. Passing an empty value
(--status "" or --investigation-status "") drops that default and matches every
value of that dimension. Sub-commands select a fixed bucket instead, and the
flags only narrow it:

  todo     runs still to investigate (not investigated/ignored and not passed)
  done     runs already investigated, ignored, or passed
  planned  tests from release plans the user owns or is assigned in

Runs are limited to the server's job validity window (30 days by default).
Rows are sorted by build_id, then build number. Examples:
  argus my-jobs --text
  argus my-jobs --status failed,test_error
  argus my-jobs --status passed --investigation-status not_investigated
  argus my-jobs --status ""    # any status, still only not_investigated/in_progress
  argus my-jobs todo --user alice
  argus my-jobs planned --status not_run`,
}

func init() {
	myjobs.Register(myJobsCmd)
	rootCmd.AddCommand(myJobsCmd)
}
