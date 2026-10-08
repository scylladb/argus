// Package search provides the top-level "argus search" command — an
// interactive discovery aid that prints the build_system_id of matching tests
// and groups so they can be copied as canonical references for the planner
// commands. It is wired into the command tree by the parent cmd package via
// [Register].
//
// Search is a discovery tool only; it is not the name-resolution path used by
// the planner commands (that uses the gridview endpoint).
package search

import (
	"strings"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// Register adds the top-level "search" command to the given parent (rootCmd).
func Register(parent *cobra.Command) {
	cmd := &cobra.Command{
		Use:   "search <query>",
		Short: "Search tests, groups, and releases for plan references",
		Long: `Search Argus for tests, groups, and releases and print their build_system_id,
which is the canonical, unambiguous way to reference a test in the planner
commands.

The query combines words and facets. Every word must match, and every facet
key must match:

  word             case-insensitive substring of the name, pretty name, or
                   build_system_id
  "two words"      a quoted phrase is one word, spaces included
  type:<value>     exact type: test, group, or release
  release:<value>  substring of the release name or pretty name
  group:<value>    substring of the group name or pretty name
  status:<value>   start of the test's latest status: status:fail, status:not
  istatus:<value>  start of the latest investigation status: istatus:not
  assignee:<value> substring of the latest run assignee's username or name
                   (status:, istatus: and assignee: need one release, from
                   --release or a release: value that names exactly one,
                   and return tests only)
  -word, -key:val  exclude what matches

Repeat a facet key to match any of its values, as in
release:2026.1 release:2026.2. Quote a facet value that holds spaces, as in
release:"ScyllaDB 2026.2". A Jenkins job URL (https://host/job/a/job/b/)
searches for its job path, a/b. A word made only of dashes, such as --, is
plain text.

A query that is a single UUID returns that release, group, test, or run.

Pass the whole query as a single shell-quoted argument, e.g.:

  argus search "release:2026.2 longevity"
  argus search 'type:group release:"ScyllaDB 2026.2"'
  argus search "longevity -azure"
  argus search https://jenkins.scylladb.com/job/scylla-master/job/longevity/
  argus search longevity-100gb --release scylla-2026.2`,
		Args: cobra.MinimumNArgs(1),
		RunE: runSearch,
	}

	cmd.Flags().StringP("release", "r", "", "Scope the search to a release (by name)")

	parent.AddCommand(cmd)
}

// runSearch is the RunE handler for "search".
func runSearch(cmd *cobra.Command, args []string) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), "search")

	// Join positional args so an unquoted multi-word query still works; the
	// backend receives the query verbatim.
	query := strings.Join(args, " ")
	releaseRef, _ := cmd.Flags().GetString("release")
	log.Debug().Str("query", query).Str("release", releaseRef).Msg("searching")

	svc := services.NewPlannerService(client, c)

	hits, err := svc.Search(ctx, query, releaseRef)
	if err != nil {
		log.Error().Err(err).Str("query", query).Msg("search failed")
		return err
	}

	log.Info().Str("query", query).Int("count", len(hits)).Msg("search completed")
	return out.Write(models.NewTabularSlice(hits))
}
