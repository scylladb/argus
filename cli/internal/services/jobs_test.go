package services_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func intPtr(n int) *int { return &n }

// newJobsSvc spins up an httptest server for mux and returns a JobsService
// wired to it with caching disabled, plus the server's base URL.
func newJobsSvc(t *testing.T, mux *http.ServeMux) (*services.JobsService, string) {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))
	return services.NewJobsService(client, ca), srv.URL
}

func registerUsers(t *testing.T, mux *http.ServeMux) {
	t.Helper()
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice"},
			"u2": {ID: "u2", Username: "bob"},
		})
	})
}

// jobsFixture covers every bucket rule: not_investigated failure (todo),
// in_progress (todo), passed but not investigated (done), investigated (done),
// ignored (done), and a run with no build number and an unknown assignee.
func jobsFixture() []models.UserJobRun {
	return []models.UserJobRun{
		{ID: "r1", BuildID: "rel/g/t1", BuildNumber: intPtr(10), BuildJobURL: "https://jenkins/job/t1/10/", ScyllaVersion: "2026.2.0~dev",
			StartTime: "2026-09-01T10:00:00.000Z", Status: "failed", InvestigationStatus: "not_investigated", Assignee: "u1"},
		{ID: "r2", BuildID: "rel/g/t0", BuildNumber: intPtr(3), BuildJobURL: "https://jenkins/job/t0/3/", ScyllaVersion: "2026.1.2",
			StartTime: "2026-09-03T10:00:00.000Z", Status: "test_error", InvestigationStatus: "in_progress", Assignee: "u1"},
		{ID: "r3", BuildID: "rel/g/t3", BuildNumber: intPtr(7),
			StartTime: "2026-09-02T10:00:00.000Z", Status: "passed", InvestigationStatus: "not_investigated", Assignee: "u1"},
		{ID: "r4", BuildID: "rel/g/t4", BuildNumber: intPtr(1),
			StartTime: "2026-08-20T10:00:00.000Z", Status: "failed", InvestigationStatus: "investigated", Assignee: "u2"},
		{ID: "r5", BuildID: "rel/g/t5", BuildNumber: nil,
			StartTime: "2026-08-25T10:00:00.000Z", Status: "aborted", InvestigationStatus: "ignored", Assignee: "ghost"},
	}
}

func ids(rows models.JobSummaries) []string {
	out := make([]string, 0, len(rows))
	for _, r := range rows {
		out = append(out, r.ID)
	}
	return out
}

func selfMux(t *testing.T) *http.ServeMux {
	t.Helper()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	mux.HandleFunc("/api/v1/user/jobs", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "GET", r.Method)
		jsonOK(t, w, jobsFixture())
	})
	return mux
}

// --------------------------------------------------------------------------
// Filters
// --------------------------------------------------------------------------

func TestDefaultRunFilter_ExcludesPassedAndSettledInvestigations(t *testing.T) {
	t.Parallel()
	f := services.DefaultRunFilter()
	assert.NotContains(t, f.Statuses, "passed")
	assert.Len(t, f.Statuses, len(services.RunStatuses)-1)
	assert.Equal(t, []string{"not_investigated", "in_progress"}, f.InvestigationStatuses)

	assert.True(t, f.Matches("failed", "not_investigated"))
	assert.True(t, f.Matches("aborted", "in_progress"))
	assert.False(t, f.Matches("passed", "not_investigated"))
	assert.False(t, f.Matches("failed", "investigated"))
	assert.False(t, f.Matches("failed", "ignored"))
}

func TestRunFilter_EmptyDimensionIsUnconstrained(t *testing.T) {
	t.Parallel()
	assert.True(t, services.RunFilter{}.Matches("passed", "ignored"))
	assert.True(t, services.RunFilter{Statuses: []string{"passed"}}.Matches("passed", "whatever"))
	assert.False(t, services.RunFilter{Statuses: []string{"passed"}}.Matches("failed", "whatever"))
}

func TestParseStatuses_ValidatesAndNormalises(t *testing.T) {
	t.Parallel()
	got, err := services.ParseStatuses([]string{" Failed", "test_error", ""})
	require.NoError(t, err)
	assert.Equal(t, []string{"failed", "test_error"}, got)

	_, err = services.ParseStatuses([]string{"failed", "bogus"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), `unknown status "bogus"`)
	assert.Contains(t, err.Error(), "not_run")

	_, err = services.ParseInvestigationStatuses([]string{"done"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), `unknown investigation status "done"`)
}

func TestFilterRuns_SectionsMirrorProfilePageRules(t *testing.T) {
	t.Parallel()
	runIDs := func(runs []models.UserJobRun) []string {
		out := make([]string, 0, len(runs))
		for _, r := range runs {
			out = append(out, r.ID)
		}
		return out
	}
	none := services.RunFilter{}
	assert.Equal(t, []string{"r1", "r2"}, runIDs(services.FilterRuns(jobsFixture(), services.SectionTodo, none)))
	assert.Equal(t, []string{"r3", "r4", "r5"}, runIDs(services.FilterRuns(jobsFixture(), services.SectionDone, none)))
	assert.Len(t, services.FilterRuns(jobsFixture(), services.SectionAll, none), 5)

	// The default filter on SectionAll is exactly the todo bucket.
	assert.Equal(t, []string{"r1", "r2"}, runIDs(services.FilterRuns(jobsFixture(), services.SectionAll, services.DefaultRunFilter())))

	// Flags narrow within a section.
	only := services.RunFilter{Statuses: []string{"failed"}}
	assert.Equal(t, []string{"r1"}, runIDs(services.FilterRuns(jobsFixture(), services.SectionTodo, only)))
	assert.Equal(t, []string{"r4"}, runIDs(services.FilterRuns(jobsFixture(), services.SectionDone, only)))
}

// --------------------------------------------------------------------------
// Runs
// --------------------------------------------------------------------------

func TestRuns_SelfUsesUserRoute(t *testing.T) {
	t.Parallel()
	svc, _ := newJobsSvc(t, selfMux(t))

	rows, err := svc.Runs(context.Background(), services.RunQuery{Section: services.SectionAll})
	require.NoError(t, err)
	assert.Len(t, rows, 5)
}

func TestRuns_UserRefUsesTeamRoute(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	mux.HandleFunc("/api/v1/user/jobs", func(w http.ResponseWriter, r *http.Request) {
		t.Error("self route must not be called with --user")
	})
	mux.HandleFunc("/api/v1/team/user/u2/jobs", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, jobsFixture()[3:4])
	})
	svc, _ := newJobsSvc(t, mux)

	done, err := svc.Runs(context.Background(), services.RunQuery{UserRef: "Bob", Section: services.SectionDone})
	require.NoError(t, err)
	require.Len(t, done, 1)
	assert.Equal(t, "r4", done[0].ID)
	assert.Equal(t, "bob", done[0].Assignee)
}

func TestRuns_UnknownUserRefErrors(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	svc, _ := newJobsSvc(t, mux)

	_, err := svc.Runs(context.Background(), services.RunQuery{UserRef: "nobody"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), `no user named "nobody"`)
}

func TestRuns_SortedByBuildIDWithURLsVersionsAndUsernames(t *testing.T) {
	t.Parallel()
	svc, base := newJobsSvc(t, selfMux(t))

	todo, err := svc.Runs(context.Background(), services.RunQuery{Section: services.SectionTodo})
	require.NoError(t, err)
	require.Equal(t, []string{"r2", "r1"}, ids(todo), "sorted by build_id")

	assert.Equal(t, "rel/g/t0", todo[0].BuildID)
	assert.Equal(t, "2026.1.2", todo[0].Version)
	assert.Equal(t, base+"/test/rel/g/t0/3", todo[0].ArgusURL)
	assert.Equal(t, "https://jenkins/job/t0/3/", todo[0].BuildJobURL)
	assert.Equal(t, "alice", todo[0].Assignee)
	assert.Equal(t, "in_progress", todo[0].InvestigationStatus)
	assert.Equal(t, "2026.2.0~dev", todo[1].Version)
}

func TestRuns_SameBuildIDOrdersByBuildNumber(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	mux.HandleFunc("/api/v1/user/jobs", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, []models.UserJobRun{
			{ID: "n12", BuildID: "rel/g/t", BuildNumber: intPtr(12), StartTime: "2026-09-01T10:00:00.000Z", Status: "failed"},
			{ID: "none", BuildID: "rel/g/t", BuildNumber: nil, StartTime: "2026-09-06T10:00:00.000Z", Status: "failed"},
			{ID: "n3", BuildID: "rel/g/t", BuildNumber: intPtr(3), StartTime: "2026-09-05T10:00:00.000Z", Status: "failed"},
			{ID: "other", BuildID: "rel/g/a", BuildNumber: intPtr(9), StartTime: "2026-09-03T10:00:00.000Z", Status: "failed"},
		})
	})
	svc, _ := newJobsSvc(t, mux)

	rows, err := svc.Runs(context.Background(), services.RunQuery{Section: services.SectionAll})
	require.NoError(t, err)
	assert.Equal(t, []string{"other", "n3", "n12", "none"}, ids(rows),
		"build_id first, then numeric build_number, runs without a number last")
}

func TestRuns_NullBuildNumberAndUnknownAssignee(t *testing.T) {
	t.Parallel()
	svc, _ := newJobsSvc(t, selfMux(t))

	done, err := svc.Runs(context.Background(), services.RunQuery{Section: services.SectionDone})
	require.NoError(t, err)
	require.Equal(t, []string{"r3", "r4", "r5"}, ids(done))

	r5 := done[2]
	assert.Nil(t, r5.BuildNumber)
	assert.Equal(t, "", r5.ArgusURL, "no build number means no stable run link")
	assert.Equal(t, "ghost", r5.Assignee, "unknown ids fall back to the raw value")
	assert.Equal(t, "", r5.Rows()[0][2])
}

func TestRuns_APIErrorPropagates(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/user/jobs", func(w http.ResponseWriter, r *http.Request) {
		jsonErr(t, w, "boom")
	})
	svc, _ := newJobsSvc(t, mux)

	_, err := svc.Runs(context.Background(), services.RunQuery{})
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrAPIError)
}

// --------------------------------------------------------------------------
// Planned
// --------------------------------------------------------------------------

func plannedFixture() []models.PlannedTest {
	return []models.PlannedTest{
		{ID: "t1", Name: "b-passed", BuildSystemID: "rel/g/b", BuildSystemURL: "https://jenkins/job/b/",
			LastRun: &models.PlannedLastRun{ID: "r1", BuildID: "rel/g/b", BuildNumber: intPtr(12), Status: "passed", ScyllaVersion: "2026.2.1",
				InvestigationStatus: "not_investigated", Assignee: "u1", BuildJobURL: "https://jenkins/job/b/12/"}},
		{ID: "t2", Name: "z-never", BuildSystemID: "rel/g/z", BuildSystemURL: "https://jenkins/job/z/"},
		{ID: "t3", Name: "a-failed", BuildSystemID: "rel/g/a",
			LastRun: &models.PlannedLastRun{ID: "r3", BuildID: "rel/g/a", BuildNumber: intPtr(2), Status: "failed", InvestigationStatus: "in_progress", Assignee: "u2"}},
		{ID: "t4", Name: "a-never", BuildSystemID: "rel/g/an", BuildSystemURL: "https://jenkins/job/an/"},
	}
}

func plannedMux(t *testing.T) *http.ServeMux {
	t.Helper()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	mux.HandleFunc("/api/v1/user/planned_jobs", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, plannedFixture())
	})
	return mux
}

func TestPlanned_SortsByBuildIDAndFillsFromLastRun(t *testing.T) {
	t.Parallel()
	svc, base := newJobsSvc(t, plannedMux(t))

	planned, err := svc.Planned(context.Background(), "", services.RunFilter{})
	require.NoError(t, err)
	require.Len(t, planned, 4)
	assert.Equal(t, []string{"rel/g/a", "rel/g/an", "rel/g/b", "rel/g/z"}, []string{
		planned[0].BuildID, planned[1].BuildID, planned[2].BuildID, planned[3].BuildID,
	}, "sorted by build_system_id")

	never := planned[1]
	assert.Equal(t, "", never.ID)
	assert.Equal(t, "not_run", never.Status)
	assert.Nil(t, never.BuildNumber)
	assert.Equal(t, "", never.Version)
	assert.Equal(t, "", never.ArgusURL)
	assert.Equal(t, "https://jenkins/job/an/", never.BuildJobURL, "job URL comes from the test when never run")
	assert.Equal(t, "", never.Assignee)

	passed := planned[2]
	assert.Equal(t, "r1", passed.ID)
	assert.Equal(t, "passed", passed.Status)
	assert.Equal(t, 12, *passed.BuildNumber)
	assert.Equal(t, "2026.2.1", passed.Version)
	assert.Equal(t, base+"/test/rel/g/b/12", passed.ArgusURL)
	assert.Equal(t, "https://jenkins/job/b/12/", passed.BuildJobURL, "last run's build URL wins when present")
	assert.Equal(t, "alice", passed.Assignee)
	assert.Equal(t, "not_investigated", passed.InvestigationStatus)
}

func TestPlanned_FiltersOnLastRunStatus(t *testing.T) {
	t.Parallel()
	svc, _ := newJobsSvc(t, plannedMux(t))

	notRun, err := svc.Planned(context.Background(), "", services.RunFilter{Statuses: []string{"not_run"}})
	require.NoError(t, err)
	assert.Equal(t, []string{"rel/g/an", "rel/g/z"}, []string{notRun[0].BuildID, notRun[1].BuildID})

	inProgress, err := svc.Planned(context.Background(), "", services.RunFilter{InvestigationStatuses: []string{"in_progress"}})
	require.NoError(t, err)
	require.Len(t, inProgress, 1)
	assert.Equal(t, "r3", inProgress[0].ID)
}

func TestPlanned_UserRefUsesTeamRoute(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerUsers(t, mux)
	mux.HandleFunc("/api/v1/team/user/u2/planned_jobs", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, []models.PlannedTest{{ID: "t9", Name: "x", BuildSystemID: "rel/g/x"}})
	})
	svc, _ := newJobsSvc(t, mux)

	planned, err := svc.Planned(context.Background(), "bob", services.RunFilter{})
	require.NoError(t, err)
	require.Len(t, planned, 1)
	assert.Equal(t, "not_run", planned[0].Status)
}

func TestFilterRuns_TodoNeverIncludesPassedRuns(t *testing.T) {
	t.Parallel()
	runs := make([]models.UserJobRun, 0, len(services.InvestigationStatuses))
	for _, inv := range services.InvestigationStatuses {
		runs = append(runs, models.UserJobRun{ID: "passed-" + inv, BuildID: "rel/g/t", Status: "passed", InvestigationStatus: inv})
	}
	assert.Empty(t, services.FilterRuns(runs, services.SectionTodo, services.RunFilter{}),
		"passed runs are done whatever their investigation status")
	assert.Len(t, services.FilterRuns(runs, services.SectionDone, services.RunFilter{}), len(runs))
}
