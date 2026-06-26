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

The query combines free text with optional facets, all AND-ed together:

  free text        case-insensitive substring match on the entity's own name
  type:<value>     exact type: test, group, or release
  release:<value>  substring match on the related release name
  group:<value>    substring match on the related group name

Facet values must NOT be quoted and cannot contain spaces. Pass the whole query
as a single shell-quoted argument, e.g.:

  argus search "release:2026.2 longevity"
  argus search "type:group release:2026.2"
  argus search longevity-100gb --release scylla-2026.2

A bare UUID query is treated as a run/entity lookup by the backend.`,
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
