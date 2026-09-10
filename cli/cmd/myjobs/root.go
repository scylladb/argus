// Package myjobs provides the "my-jobs" cobra command and its todo / done /
// planned sub-commands, which list the runs assigned to a user and the tests
// planned for them. It is wired into the command tree by the parent cmd package
// via [Register].
package myjobs

import (
	"context"
	"strings"

	"github.com/scylladb/argus/cli/internal/cmdctx"
	"github.com/scylladb/argus/cli/internal/logging"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
)

// fetchFunc produces one listing for the given --user reference and filter.
// Its receiver-first shape lets JobsService methods be passed as method
// expressions.
type fetchFunc func(svc *services.JobsService, ctx context.Context, userRef string, filter services.RunFilter) (models.JobSummaries, error)

// Register adds the persistent --user / --status / --investigation-status
// flags and the filtered-run-list handler to parent (the "my-jobs" command
// owned by the cmd package), then registers the todo, done and planned
// sub-commands on it.
func Register(parent *cobra.Command) {
	parent.PersistentFlags().StringP("user", "u", "", "Username whose jobs to show (defaults to the caller)")
	parent.PersistentFlags().StringSliceP("status", "s", nil,
		"Only runs with these statuses (repeatable or comma-separated); an empty value (--status \"\") lifts the filter and returns every status: "+strings.Join(services.RunStatuses, ", "))
	parent.PersistentFlags().StringSliceP("investigation-status", "i", nil,
		"Only runs with these investigation statuses (repeatable or comma-separated); an empty value lifts the filter and returns every investigation status: "+strings.Join(services.InvestigationStatuses, ", "))
	parent.Args = cobra.NoArgs
	parent.RunE = func(cmd *cobra.Command, _ []string) error {
		return run(cmd, "my-jobs", true, sectionFetch(services.SectionAll))
	}

	registerSection(parent, "todo", "Runs assigned to the user that still need investigation",
		`List runs assigned to the user whose investigation status is neither
"investigated" nor "ignored" and whose run status is not "passed".
--status / --investigation-status narrow the list further.`,
		sectionFetch(services.SectionTodo))
	registerSection(parent, "done", "Runs assigned to the user that are investigated, ignored, or passed",
		`List runs assigned to the user that were marked investigated or ignored,
or that passed. --status / --investigation-status narrow the list further.`,
		sectionFetch(services.SectionDone))
	registerSection(parent, "planned", "Tests the user is planned to execute",
		`List enabled tests from release plans the user owns (unassigned or assigned
to them) or participates in (assigned to them), each with its latest run.
Tests that never ran report status "not_run" with an empty run id.
--status / --investigation-status match against the latest run.`,
		(*services.JobsService).Planned)
}

// sectionFetch adapts a run section to a fetchFunc.
func sectionFetch(section services.Section) fetchFunc {
	return func(svc *services.JobsService, ctx context.Context, userRef string, filter services.RunFilter) (models.JobSummaries, error) {
		return svc.Runs(ctx, services.RunQuery{UserRef: userRef, Section: section, Filter: filter})
	}
}

// registerSection adds one sub-command to parent.
func registerSection(parent *cobra.Command, use, short, long string, fetch fetchFunc) {
	cmd := &cobra.Command{
		Use:   use,
		Short: short,
		Long:  long,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return run(cmd, "my-jobs-"+use, false, fetch)
		},
	}
	parent.AddCommand(cmd)
}

// filterFromFlags reads --status / --investigation-status. When useDefaults is
// set, a flag that was not given falls back to the corresponding
// [services.DefaultRunFilter] dimension; otherwise it leaves that dimension
// unconstrained.
func filterFromFlags(cmd *cobra.Command, useDefaults bool) (services.RunFilter, error) {
	var filter services.RunFilter
	if useDefaults {
		filter = services.DefaultRunFilter()
	}
	if cmd.Flags().Changed("status") {
		raw, _ := cmd.Flags().GetStringSlice("status")
		statuses, err := services.ParseStatuses(raw)
		if err != nil {
			return services.RunFilter{}, err
		}
		filter.Statuses = statuses
	}
	if cmd.Flags().Changed("investigation-status") {
		raw, _ := cmd.Flags().GetStringSlice("investigation-status")
		statuses, err := services.ParseInvestigationStatuses(raw)
		if err != nil {
			return services.RunFilter{}, err
		}
		filter.InvestigationStatuses = statuses
	}
	return filter, nil
}

// run is the shared RunE body for the parent and every sub-command.
func run(cmd *cobra.Command, component string, useDefaults bool, fetch fetchFunc) error {
	cmd.SilenceUsage = true
	ctx := cmd.Context()
	client := cmdctx.APIClientFrom(ctx)
	out := cmdctx.OutputterFrom(ctx)
	c := cmdctx.CacheFrom(ctx)
	log := logging.For(cmdctx.LoggerFrom(ctx), component)

	userRef, _ := cmd.Flags().GetString("user")
	filter, err := filterFromFlags(cmd, useDefaults)
	if err != nil {
		log.Error().Err(err).Msg("invalid filter")
		return err
	}
	log.Debug().Str("user", userRef).
		Strs("status", filter.Statuses).
		Strs("investigation_status", filter.InvestigationStatuses).
		Msg("listing jobs")

	svc := services.NewJobsService(client, c)

	rows, err := fetch(svc, ctx, userRef, filter)
	if err != nil {
		log.Error().Err(err).Str("user", userRef).Msg("failed to list jobs")
		return err
	}

	log.Info().Int("count", len(rows)).Msg("jobs listed successfully")
	return out.Write(rows)
}
