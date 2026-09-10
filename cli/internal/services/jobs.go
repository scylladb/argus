package services

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// JobsService backs the `my-jobs` command: it fetches the runs assigned to a
// user and the tests planned for them, applies status filters, and flattens
// both into display rows with usernames and web links resolved.
type JobsService struct {
	client *api.Client
	users  *UserService
}

// NewJobsService constructs a [JobsService].
func NewJobsService(client *api.Client, c *cache.Cache) *JobsService {
	return &JobsService{client: client, users: NewUserService(client, c)}
}

// RunStatuses are the run status values accepted by --status, in the order the
// backend enum defines them.
var RunStatuses = []string{"created", "running", "failed", "test_error", "error", "passed", "aborted", "not_planned", "not_run"}

// InvestigationStatuses are the values accepted by --investigation-status.
var InvestigationStatuses = []string{"not_investigated", "in_progress", "investigated", "ignored"}

// RunFilter narrows runs by status and investigation status. An empty list
// places no constraint on that dimension.
type RunFilter struct {
	Statuses              []string
	InvestigationStatuses []string
}

// DefaultRunFilter is what a bare `my-jobs` shows: anything not passed that is
// still not investigated or only in progress.
func DefaultRunFilter() RunFilter {
	statuses := make([]string, 0, len(RunStatuses)-1)
	for _, s := range RunStatuses {
		if s != "passed" {
			statuses = append(statuses, s)
		}
	}
	return RunFilter{
		Statuses:              statuses,
		InvestigationStatuses: []string{"not_investigated", "in_progress"},
	}
}

// Matches reports whether a run with the given statuses passes the filter.
func (f RunFilter) Matches(status, investigation string) bool {
	return containsOrEmpty(f.Statuses, status) && containsOrEmpty(f.InvestigationStatuses, investigation)
}

func containsOrEmpty(allowed []string, v string) bool {
	if len(allowed) == 0 {
		return true
	}
	for _, a := range allowed {
		if a == v {
			return true
		}
	}
	return false
}

// ParseStatuses validates user-supplied run statuses (case-insensitive) against
// [RunStatuses].
func ParseStatuses(values []string) ([]string, error) {
	return parseEnum(values, RunStatuses, "status")
}

// ParseInvestigationStatuses validates user-supplied investigation statuses
// (case-insensitive) against [InvestigationStatuses].
func ParseInvestigationStatuses(values []string) ([]string, error) {
	return parseEnum(values, InvestigationStatuses, "investigation status")
}

func parseEnum(values, allowed []string, what string) ([]string, error) {
	out := make([]string, 0, len(values))
	for _, v := range values {
		v = strings.ToLower(strings.TrimSpace(v))
		if v == "" {
			continue
		}
		if !containsOrEmpty(allowed, v) {
			return nil, fmt.Errorf("unknown %s %q (expected one of: %s)", what, v, strings.Join(allowed, ", "))
		}
		out = append(out, v)
	}
	return out, nil
}

// Section selects which assigned runs a query starts from before filtering.
type Section int

const (
	// SectionAll starts from every assigned run.
	SectionAll Section = iota
	// SectionTodo starts from runs still to investigate: not investigated or
	// ignored, and not passed.
	SectionTodo
	// SectionDone starts from the complement of SectionTodo.
	SectionDone
)

// RunQuery describes one `my-jobs` run listing.
type RunQuery struct {
	// UserRef is the --user value; empty means the caller.
	UserRef string
	Section Section
	Filter  RunFilter
}

// ResolveTargetUser turns the --user reference into a user UUID. An empty ref
// means the caller and yields an empty id.
func (s *JobsService) ResolveTargetUser(ctx context.Context, ref string) (string, error) {
	if ref == "" {
		return "", nil
	}
	return s.users.ResolveUserID(ctx, ref)
}

// ListRuns returns the runs assigned to userID, or to the caller when userID is
// empty, sorted by build_id then build_number (runs without a number last).
func (s *JobsService) ListRuns(ctx context.Context, userID string) ([]models.UserJobRun, error) {
	route := api.UserJobs
	if userID != "" {
		route = fmt.Sprintf(api.TeamUserJobs, userID)
	}
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	runs, err := api.DoJSON[[]models.UserJobRun](s.client, req)
	if err != nil {
		return nil, err
	}
	sort.SliceStable(runs, func(i, j int) bool {
		if runs[i].BuildID != runs[j].BuildID {
			return runs[i].BuildID < runs[j].BuildID
		}
		ni, nj := runs[i].BuildNumber, runs[j].BuildNumber
		switch {
		case ni == nil && nj == nil:
			return runs[i].StartTime < runs[j].StartTime
		case ni == nil:
			return false
		case nj == nil:
			return true
		}
		return *ni < *nj
	})
	return runs, nil
}

// ListPlanned returns the tests planned for userID, or for the caller when
// userID is empty, sorted by build_system_id.
func (s *JobsService) ListPlanned(ctx context.Context, userID string) ([]models.PlannedTest, error) {
	route := api.UserPlannedJobs
	if userID != "" {
		route = fmt.Sprintf(api.TeamUserPlannedJobs, userID)
	}
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	tests, err := api.DoJSON[[]models.PlannedTest](s.client, req)
	if err != nil {
		return nil, err
	}
	sort.SliceStable(tests, func(i, j int) bool { return tests[i].BuildSystemID < tests[j].BuildSystemID })
	return tests, nil
}

// plannedStatus is the status shown for a planned test: its last run's status,
// or "not_run" when it has never run.
func plannedStatus(t models.PlannedTest) string {
	if t.LastRun == nil || t.LastRun.Status == "" {
		return "not_run"
	}
	return t.LastRun.Status
}

// IsRunDone reports whether a run belongs in the "done" bucket: investigated or
// ignored, or passed regardless of investigation. Everything else is to-do.
func IsRunDone(run models.UserJobRun) bool {
	switch run.InvestigationStatus {
	case "investigated", "ignored":
		return true
	}
	return run.Status == "passed"
}

// inSection reports whether run belongs to section.
func inSection(run models.UserJobRun, section Section) bool {
	switch section {
	case SectionTodo:
		return !IsRunDone(run)
	case SectionDone:
		return IsRunDone(run)
	default:
		return true
	}
}

// FilterRuns keeps the runs that belong to section and pass filter, preserving
// order.
func FilterRuns(runs []models.UserJobRun, section Section, filter RunFilter) []models.UserJobRun {
	out := make([]models.UserJobRun, 0, len(runs))
	for _, run := range runs {
		if inSection(run, section) && filter.Matches(run.Status, run.InvestigationStatus) {
			out = append(out, run)
		}
	}
	return out
}

// FilterPlanned keeps the planned tests whose displayed status (the last run's,
// or "not_run") and investigation status pass filter, preserving order.
func FilterPlanned(tests []models.PlannedTest, filter RunFilter) []models.PlannedTest {
	out := make([]models.PlannedTest, 0, len(tests))
	for _, t := range tests {
		investigation := ""
		if t.LastRun != nil {
			investigation = t.LastRun.InvestigationStatus
		}
		if filter.Matches(plannedStatus(t), investigation) {
			out = append(out, t)
		}
	}
	return out
}

// derefInt returns the pointed-to value, or 0 for a nil pointer.
func derefInt(n *int) int {
	if n == nil {
		return 0
	}
	return *n
}

// SummarizeRuns flattens runs into display rows, resolving assignee UUIDs to
// usernames and attaching the Argus web link.
func (s *JobsService) SummarizeRuns(ctx context.Context, runs []models.UserJobRun) (models.JobSummaries, error) {
	out := make(models.JobSummaries, 0, len(runs))
	for _, run := range runs {
		assignee, err := s.users.UsernameByID(ctx, run.Assignee)
		if err != nil {
			return nil, err
		}
		out = append(out, models.JobSummary{
			ID:                  run.ID,
			BuildID:             run.BuildID,
			BuildNumber:         run.BuildNumber,
			Version:             run.ScyllaVersion,
			BuildJobURL:         run.BuildJobURL,
			ArgusURL:            api.RunURL(s.client.BaseURL(), run.BuildID, derefInt(run.BuildNumber)),
			Status:              run.Status,
			InvestigationStatus: run.InvestigationStatus,
			Assignee:            assignee,
		})
	}
	return out, nil
}

// SummarizePlanned flattens planned tests into display rows. Run-derived
// columns come from the last run when there is one; a never-run test reports
// status "not_run" and leaves them empty.
func (s *JobsService) SummarizePlanned(ctx context.Context, tests []models.PlannedTest) (models.JobSummaries, error) {
	out := make(models.JobSummaries, 0, len(tests))
	for _, t := range tests {
		row := models.JobSummary{
			BuildID:     t.BuildSystemID,
			BuildJobURL: t.BuildSystemURL,
			Status:      "not_run",
		}
		if lr := t.LastRun; lr != nil {
			assignee, err := s.users.UsernameByID(ctx, lr.Assignee)
			if err != nil {
				return nil, err
			}
			row.ID = lr.ID
			row.BuildNumber = lr.BuildNumber
			row.Version = lr.ScyllaVersion
			row.ArgusURL = api.RunURL(s.client.BaseURL(), t.BuildSystemID, derefInt(lr.BuildNumber))
			row.Status = plannedStatus(t)
			row.InvestigationStatus = lr.InvestigationStatus
			row.Assignee = assignee
			if lr.BuildJobURL != "" {
				row.BuildJobURL = lr.BuildJobURL
			}
		}
		out = append(out, row)
	}
	return out, nil
}

// Runs lists the assigned runs selected by q as display rows.
func (s *JobsService) Runs(ctx context.Context, q RunQuery) (models.JobSummaries, error) {
	userID, err := s.ResolveTargetUser(ctx, q.UserRef)
	if err != nil {
		return nil, err
	}
	runs, err := s.ListRuns(ctx, userID)
	if err != nil {
		return nil, err
	}
	return s.SummarizeRuns(ctx, FilterRuns(runs, q.Section, q.Filter))
}

// Planned lists the tests planned for userRef (empty for the caller) that pass
// filter, as display rows.
func (s *JobsService) Planned(ctx context.Context, userRef string, filter RunFilter) (models.JobSummaries, error) {
	userID, err := s.ResolveTargetUser(ctx, userRef)
	if err != nil {
		return nil, err
	}
	tests, err := s.ListPlanned(ctx, userID)
	if err != nil {
		return nil, err
	}
	return s.SummarizePlanned(ctx, FilterPlanned(tests, filter))
}
