package services_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// jsonErr writes the standard Argus error envelope.
func jsonErr(t *testing.T, w http.ResponseWriter, message string) {
	t.Helper()
	env := map[string]json.RawMessage{
		"status":   json.RawMessage(`"error"`),
		"response": json.RawMessage(`{"exception":"PlannerServiceException","message":` + mustJSON(t, message) + `,"arguments":[]}`),
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	require.NoError(t, json.NewEncoder(w).Encode(env))
}

func mustJSON(t *testing.T, v any) string {
	t.Helper()
	raw, err := json.Marshal(v)
	require.NoError(t, err)
	return string(raw)
}

func newPlannerSvc(t *testing.T, mux *http.ServeMux) *services.PlannerService {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))
	return services.NewPlannerService(client, ca)
}

// gridviewFixture builds a small release structure with an ambiguous bare test
// name ("longevity-100gb" in two groups) and a disabled test in tier1.
func gridviewFixture() models.GridView {
	return models.GridView{
		Groups: map[string]models.GridEntity{
			"g1": {ID: "g1", Name: "tier1", PrettyName: "Tier 1", Type: "group",
				BuildSystemID: "scylla-2026.2/tier1"},
			"g2": {ID: "g2", Name: "tier2", PrettyName: "Tier 2", Type: "group",
				BuildSystemID: "scylla-2026.2/tier2"},
		},
		Tests: map[string]models.GridEntity{
			"t1": {ID: "t1", Name: "longevity-100gb", GroupID: "g1", Group: "Tier 1",
				BuildSystemID: "scylla-2026.2/tier1/longevity-100gb", Enabled: true},
			"t2": {ID: "t2", Name: "longevity-200gb", GroupID: "g1", Group: "Tier 1",
				BuildSystemID: "scylla-2026.2/tier1/longevity-200gb", Enabled: true},
			"t3": {ID: "t3", Name: "longevity-100gb", GroupID: "g2", Group: "Tier 2",
				BuildSystemID: "scylla-2026.2/tier2/longevity-100gb", Enabled: true},
			"t4": {ID: "t4", Name: "longevity-disabled", GroupID: "g1", Group: "Tier 1",
				BuildSystemID: "scylla-2026.2/tier1/longevity-disabled", Enabled: false},
		},
	}
}

// --------------------------------------------------------------------------
// Plan reads
// --------------------------------------------------------------------------

func TestPlannerService_GetPlansForRelease(t *testing.T) {
	t.Parallel()
	plans := []models.ReleasePlan{
		{ID: "p1", Key: "scylla-2026.2#1", Name: "Longevity"},
		{ID: "p2", Key: "scylla-2026.2#2", Name: "Upgrade"},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/release/rel-1/all", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "GET", r.Method)
		jsonOK(t, w, plans)
	})
	svc := newPlannerSvc(t, mux)

	got, err := svc.GetPlansForRelease(context.Background(), "rel-1")
	require.NoError(t, err)
	require.Len(t, got, 2)
	assert.Equal(t, "scylla-2026.2#1", got[0].Key)
}

func TestPlannerService_GetPlan(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/scylla-2026.2#3/get", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ReleasePlan{ID: "p3", Key: "scylla-2026.2#3", Name: "GA"})
	})
	svc := newPlannerSvc(t, mux)

	got, err := svc.GetPlan(context.Background(), "scylla-2026.2#3")
	require.NoError(t, err)
	assert.Equal(t, "p3", got.ID)
}

func TestPlannerService_GetPlan_BackendError(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/missing/get", func(w http.ResponseWriter, r *http.Request) {
		jsonErr(t, w, "Plan not found")
	})
	svc := newPlannerSvc(t, mux)

	_, err := svc.GetPlan(context.Background(), "missing")
	require.Error(t, err)
	var apiErr *api.APIError
	require.True(t, errors.As(err, &apiErr))
	assert.Equal(t, "Plan not found", apiErr.Body.Message)
}

// --------------------------------------------------------------------------
// Release resolution
// --------------------------------------------------------------------------

func releasesMux(t *testing.T, calls *int32) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/releases", func(w http.ResponseWriter, r *http.Request) {
		if calls != nil {
			atomic.AddInt32(calls, 1)
		}
		jsonOK(t, w, []models.Release{
			{ID: "rel-1", Name: "scylla-2026.2", Enabled: true},
			{ID: "rel-2", Name: "scylla-2026.1", Enabled: false},
		})
	})
	return mux
}

func TestPlannerService_ResolveReleaseID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, releasesMux(t, nil))

	// Exact name, case-insensitive.
	id, err := svc.ResolveReleaseID(context.Background(), "Scylla-2026.2")
	require.NoError(t, err)
	assert.Equal(t, "rel-1", id)
}

func TestPlannerService_ResolveReleaseID_NoMatch(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, releasesMux(t, nil))

	_, err := svc.ResolveReleaseID(context.Background(), "scylla-9999")
	require.Error(t, err)
}

func TestPlannerService_ResolveReleaseID_RawUUIDRejected(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, releasesMux(t, nil))

	// A raw UUID is not a release name and must not silently resolve.
	_, err := svc.ResolveReleaseID(context.Background(), "7f3c1e90-0000-0000-0000-000000000000")
	require.Error(t, err)
}

// --------------------------------------------------------------------------
// User resolution
// --------------------------------------------------------------------------

func usersMux(t *testing.T) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice"},
			"u2": {ID: "u2", Username: "bob"},
		})
	})
	return mux
}

func TestPlannerService_ResolveUserID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, usersMux(t))

	id, err := svc.ResolveUserID(context.Background(), "Alice")
	require.NoError(t, err)
	assert.Equal(t, "u1", id)
}

func TestPlannerService_ResolveUserID_NoMatch(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, usersMux(t))

	_, err := svc.ResolveUserID(context.Background(), "carol")
	require.Error(t, err)
}

// --------------------------------------------------------------------------
// Test / group resolution
// --------------------------------------------------------------------------

func gridviewMux(t *testing.T, calls *int32) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		if calls != nil {
			atomic.AddInt32(calls, 1)
		}
		jsonOK(t, w, gridviewFixture())
	})
	return mux
}

func TestPlannerService_ResolveEntityID_BuildSystemID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	id, err := svc.ResolveEntityID(context.Background(),
		"scylla-2026.2/tier2/longevity-100gb", "rel-1", services.KindTest)
	require.NoError(t, err)
	assert.Equal(t, "t3", id)
}

func TestPlannerService_ResolveEntityID_GroupQualified(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	// Bare name is ambiguous, but group-qualified disambiguates.
	id, err := svc.ResolveEntityID(context.Background(),
		"tier1/longevity-100gb", "rel-1", services.KindTest)
	require.NoError(t, err)
	assert.Equal(t, "t1", id)
}

func TestPlannerService_ResolveEntityID_BareUnique(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	id, err := svc.ResolveEntityID(context.Background(),
		"longevity-200gb", "rel-1", services.KindTest)
	require.NoError(t, err)
	assert.Equal(t, "t2", id)
}

func TestPlannerService_ResolveEntityID_BareAmbiguous(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	_, err := svc.ResolveEntityID(context.Background(),
		"longevity-100gb", "rel-1", services.KindTest)
	require.Error(t, err)
	// Candidate list surfaces build_system_id, group, and UUID.
	assert.Contains(t, err.Error(), "scylla-2026.2/tier1/longevity-100gb")
	assert.Contains(t, err.Error(), "scylla-2026.2/tier2/longevity-100gb")
}

func TestPlannerService_ResolveEntityID_Group(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	id, err := svc.ResolveEntityID(context.Background(), "tier1", "rel-1", services.KindGroup)
	require.NoError(t, err)
	assert.Equal(t, "g1", id)
}

func TestPlannerService_ResolveEntityID_GroupByBuildSystemID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	// A group's fully-qualified build_system_id ("release/group") resolves too.
	id, err := svc.ResolveEntityID(context.Background(),
		"scylla-2026.2/tier1", "rel-1", services.KindGroup)
	require.NoError(t, err)
	assert.Equal(t, "g1", id)
}

func TestPlannerService_ExpandGroup_EnabledOnly(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	ids, err := svc.ExpandGroup(context.Background(), "rel-1", "tier1")
	require.NoError(t, err)
	// t1 + t2 are enabled in tier1; t4 is disabled and must be excluded.
	assert.Equal(t, []string{"t1", "t2"}, ids)
}

func TestPlannerService_ExpandGroup_ByBuildSystemID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	// A group referenced by build_system_id fans out to its enabled tests.
	ids, err := svc.ExpandGroup(context.Background(), "rel-1", "scylla-2026.2/tier1")
	require.NoError(t, err)
	assert.Equal(t, []string{"t1", "t2"}, ids)
}

func TestPlannerService_GetReleaseOverview(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	overview, err := svc.GetReleaseOverview(context.Background(), "rel-1")
	require.NoError(t, err)
	// Every test is keyed by group/test and valued by its build_system_id.
	assert.Equal(t, models.ReleaseGrid{
		"Tier 1/longevity-100gb":    "scylla-2026.2/tier1/longevity-100gb",
		"Tier 1/longevity-200gb":    "scylla-2026.2/tier1/longevity-200gb",
		"Tier 1/longevity-disabled": "scylla-2026.2/tier1/longevity-disabled",
		"Tier 2/longevity-100gb":    "scylla-2026.2/tier2/longevity-100gb",
	}, overview)
}

func TestPlannerService_Resolution_SingleGridviewFetch(t *testing.T) {
	t.Parallel()
	var calls int32
	svc := newPlannerSvc(t, gridviewMux(t, &calls))

	ctx := context.Background()
	_, err := svc.ResolveEntityID(ctx, "tier1/longevity-100gb", "rel-1", services.KindTest)
	require.NoError(t, err)
	_, err = svc.ResolveEntityID(ctx, "tier1", "rel-1", services.KindGroup)
	require.NoError(t, err)
	_, err = svc.ExpandGroup(ctx, "rel-1", "tier1")
	require.NoError(t, err)

	assert.Equal(t, int32(1), atomic.LoadInt32(&calls), "gridview should be fetched once")
}

// --------------------------------------------------------------------------
// Search
// --------------------------------------------------------------------------

// searchFixture is a search response with the synthetic "Add all..." special
// row first (as the backend always prepends it), followed by real hits.
func searchFixture() models.SearchResponse {
	return models.SearchResponse{
		Total: 3,
		Hits: []models.SearchHit{
			{ID: "db6f33b2-660b-4639-ba7f-79725ef96616", Name: "Add all...", Type: "special"},
			{ID: "t1", Name: "longevity-100gb", Type: "test",
				BuildSystemID: "scylla-2026.2/tier1/longevity-100gb", Enabled: true,
				Group: &models.SearchRef{ID: "g1", Name: "tier1"}},
			{ID: "g1", Name: "tier1", Type: "group", BuildSystemID: "scylla-2026.2/tier1"},
		},
	}
}

func TestPlannerService_Search_FiltersSpecialRow(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/search", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "GET", r.Method)
		jsonOK(t, w, searchFixture())
	})
	svc := newPlannerSvc(t, mux)

	hits, err := svc.Search(context.Background(), "longevity", "")
	require.NoError(t, err)
	// The "special" Add-all row is dropped; only the real test and group remain.
	require.Len(t, hits, 2)
	for _, h := range hits {
		assert.NotEqual(t, "special", h.Type)
	}
	assert.Equal(t, "t1", hits[0].ID)
	assert.Equal(t, "g1", hits[1].ID)
}

func TestPlannerService_Search_QueryPassthroughNoRelease(t *testing.T) {
	t.Parallel()
	var gotQuery string
	var hasReleaseID bool
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/search", func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.Query().Get("query")
		_, hasReleaseID = r.URL.Query()["releaseId"]
		jsonOK(t, w, searchFixture())
	})
	svc := newPlannerSvc(t, mux)

	// Free text + facets are passed through verbatim; no releaseId when unscoped.
	_, err := svc.Search(context.Background(), "type:group release:2026.2", "")
	require.NoError(t, err)
	assert.Equal(t, "type:group release:2026.2", gotQuery)
	assert.False(t, hasReleaseID, "releaseId must be absent when no release is given")
}

func TestPlannerService_Search_ScopesByRelease(t *testing.T) {
	t.Parallel()
	var gotReleaseID string
	mux := releasesMux(t, nil)
	mux.HandleFunc("/api/v1/planning/search", func(w http.ResponseWriter, r *http.Request) {
		gotReleaseID = r.URL.Query().Get("releaseId")
		jsonOK(t, w, searchFixture())
	})
	svc := newPlannerSvc(t, mux)

	// The --release name resolves to its UUID and is sent as releaseId.
	_, err := svc.Search(context.Background(), "longevity", "scylla-2026.2")
	require.NoError(t, err)
	assert.Equal(t, "rel-1", gotReleaseID)
}

func TestPlannerService_Search_UnknownReleaseErrors(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, releasesMux(t, nil))

	_, err := svc.Search(context.Background(), "longevity", "scylla-9999")
	require.Error(t, err)
}

func TestPlannerService_Search_BackendError(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/search", func(w http.ResponseWriter, r *http.Request) {
		jsonErr(t, w, "search failed")
	})
	svc := newPlannerSvc(t, mux)

	_, err := svc.Search(context.Background(), "longevity", "")
	require.Error(t, err)
	var apiErr *api.APIError
	require.True(t, errors.As(err, &apiErr))
	assert.Equal(t, "search failed", apiErr.Body.Message)
}

// --------------------------------------------------------------------------
// Create / Delete (Phase 4)
// --------------------------------------------------------------------------

// resolveMux serves the releases, users, and gridview endpoints so name-based
// references in a template resolve to UUIDs.
func resolveMux(t *testing.T) *http.ServeMux {
	t.Helper()
	mux := releasesMux(t, nil)
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice"},
			"u2": {ID: "u2", Username: "bob"},
		})
	})
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, gridviewFixture())
	})
	return mux
}

// av wraps a reference→assignee string map into the assignments map that
// PlanTemplate/PlanUpdateSpec now use (assignee only, no labels), keeping the
// existing table data terse.
func av(m map[string]string) map[string]models.AssignmentValue {
	out := make(map[string]models.AssignmentValue, len(m))
	for k, v := range m {
		out[k] = models.AssignmentValue{Assignee: v}
	}
	return out
}

func TestPlannerService_BuildCreateRequest_ResolvesAndExpands(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	tmpl := models.PlanTemplate{
		Name:          "2026.2 Longevity",
		Release:       "scylla-2026.2",
		Owner:         "alice",
		TargetVersion: "2026.2.0",
		Assignments: av(map[string]string{
			"tier1/longevity-200gb": "$owner",
			"tier2/longevity-100gb": "bob",
		}),
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)

	assert.Equal(t, "rel-1", req.ReleaseID)
	assert.Equal(t, "u1", req.Owner)
	// bob is assigned; owner-marked tests do not add a participant.
	assert.Equal(t, []string{"u2"}, req.Participants)
	// Both entities join tests; only the specific assignee enters the mapping.
	assert.ElementsMatch(t, []string{"t2", "t3"}, req.Tests)
	assert.Equal(t, map[string]string{"t3": "u2"}, req.Assignments)
	// Collections must serialise as [] / {}, never null (backend requires keys).
	assert.NotNil(t, req.Groups)
	assert.Empty(t, req.Groups)
}

func TestPlannerService_BuildCreateRequest_GroupAssignmentFansOut(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	tmpl := models.PlanTemplate{
		Name:        "fanout",
		Release:     "scylla-2026.2",
		Owner:       "alice",
		Assignments: av(map[string]string{"tier1": "bob"}),
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)
	// A group assignment fans out to each enabled member test (t1, t2).
	assert.Equal(t, map[string]string{"t1": "u2", "t2": "u2"}, req.Assignments)
	assert.ElementsMatch(t, []string{"t1", "t2"}, req.Tests)
}

func TestPlannerService_BuildCreateRequest_GroupByBuildSystemID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Referencing a group by its fully-qualified build_system_id must resolve
	// and fan out, not fail with "group not found".
	tmpl := models.PlanTemplate{
		Name:        "fanout-bsid",
		Release:     "scylla-2026.2",
		Owner:       "alice",
		Assignments: av(map[string]string{"scylla-2026.2/tier1": "bob"}),
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.Equal(t, map[string]string{"t1": "u2", "t2": "u2"}, req.Assignments)
	assert.ElementsMatch(t, []string{"t1", "t2"}, req.Tests)
}

// TestPlannerService_BuildCreateRequest_NoPhantomParticipants guards against a
// race loser being left as a participant. When a group entry and a specific
// test entry both claim the same test, only one assignee wins the mapping (map
// iteration order is randomised). Participants must be derived from the settled
// assignment map, so the loser — who holds no assignment — never appears.
func TestPlannerService_BuildCreateRequest_NoPhantomParticipants(t *testing.T) {
	t.Parallel()
	// Three users so the owner (carol) is distinct from both contenders.
	mux := releasesMux(t, nil)
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice"},
			"u2": {ID: "u2", Username: "bob"},
			"u3": {ID: "u3", Username: "carol"},
		})
	})
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, gridviewFixture())
	})
	svc := newPlannerSvc(t, mux)

	tmpl := models.PlanTemplate{
		Name:    "phantom",
		Release: "scylla-2026.2",
		Owner:   "carol",
		Assignments: av(map[string]string{
			"tier1":                 "bob",   // fans out to t1, t2
			"tier1/longevity-200gb": "alice", // contends for t2
		}),
	}

	// Map iteration order is randomised per range, so repeat to exercise both
	// orderings and catch a phantom regardless of which entry settles t2.
	for i := 0; i < 50; i++ {
		req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
		require.NoError(t, err)
		assert.Empty(t, warnings)

		// Every participant must hold at least one assignment in the plan.
		holders := map[string]bool{}
		for _, userID := range req.Assignments {
			holders[userID] = true
		}
		for _, p := range req.Participants {
			assert.Contains(t, holders, p, "participant %q holds no assignment (phantom)", p)
			assert.NotEqual(t, "u3", p, "owner must not be listed as a participant")
		}
	}
}

func TestPlannerService_BuildCreateRequest_OwnerMarkerLeavesUnassigned(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	tmpl := models.PlanTemplate{
		Name:        "p",
		Release:     "scylla-2026.2",
		Owner:       "alice",
		Assignments: av(map[string]string{"tier1/longevity-100gb": "$owner"}),
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)
	// $owner test is in tests but absent from assignments; no participant.
	assert.Equal(t, []string{"t1"}, req.Tests)
	assert.Empty(t, req.Assignments)
	assert.Empty(t, req.Participants)
}

func TestPlannerService_BuildCreateRequest_MissingTestWarnsAndOmits(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	tmpl := models.PlanTemplate{
		Name:    "p",
		Release: "scylla-2026.2",
		Owner:   "alice",
		Assignments: av(map[string]string{
			"tier1/longevity-200gb": "$owner",
			"tier1/does-not-exist":  "$owner",
		}),
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	// Missing test is omitted (plan still created) and reported as a warning.
	assert.Equal(t, []string{"t2"}, req.Tests)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "does-not-exist")
}

func TestPlannerService_BuildCreateRequest_AmbiguousAborts(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	tmpl := models.PlanTemplate{
		Name:        "p",
		Release:     "scylla-2026.2",
		Owner:       "alice",
		Assignments: av(map[string]string{"longevity-100gb": "$owner"}), // in tier1 and tier2
	}

	_, _, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.Error(t, err)
	assert.True(t, errors.Is(err, services.ErrAmbiguousEntity))
}

func TestPlannerService_BuildCreateRequest_AllMissingTestsRejected(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Every entity is absent from the release gridview, so all are omitted and
	// the plan would have no tests — reject and list the missing entities
	// instead of sending an empty (null) tests list the backend can't iterate.
	tmpl := models.PlanTemplate{
		Name:        "p",
		Release:     "scylla-2026.2",
		Owner:       "alice",
		Assignments: av(map[string]string{"tier1/gone-a": "$owner", "tier1/gone-b": "$owner"}),
	}

	_, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.Error(t, err)
	assert.Len(t, warnings, 2)
	assert.Contains(t, err.Error(), "no tests resolved")
	assert.Contains(t, err.Error(), "tier1/gone-a")
	assert.Contains(t, err.Error(), "tier1/gone-b")
}

func TestPlannerService_BuildCreateRequest_EmptyAssignmentsRejected(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	_, _, err := svc.BuildCreateRequest(context.Background(),
		models.PlanTemplate{Name: "p", Release: "scylla-2026.2", Owner: "alice"})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "at least one test")
}

func TestPlannerService_BuildCreateRequest_RequiresReleaseAndOwner(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	_, _, err := svc.BuildCreateRequest(context.Background(),
		models.PlanTemplate{Name: "p", Owner: "alice"})
	require.Error(t, err)

	_, _, err = svc.BuildCreateRequest(context.Background(),
		models.PlanTemplate{Name: "p", Release: "scylla-2026.2"})
	require.Error(t, err)
}

func TestPlannerService_CreatePlan_PostsAndReturns(t *testing.T) {
	t.Parallel()
	var gotBody models.CreatePlanRequest
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/create", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "POST", r.Method)
		require.NoError(t, json.NewDecoder(r.Body).Decode(&gotBody))
		jsonOK(t, w, models.ReleasePlan{ID: "p9", Key: "scylla-2026.2#9", Name: gotBody.Name})
	})
	svc := newPlannerSvc(t, mux)

	plan, err := svc.CreatePlan(context.Background(), models.CreatePlanRequest{
		Name: "GA", ReleaseID: "rel-1", Owner: "u1",
		Tests: []string{"t1"}, Groups: []string{}, Assignments: map[string]string{},
	})
	require.NoError(t, err)
	assert.Equal(t, "p9", plan.ID)
	assert.Equal(t, "GA", gotBody.Name)
}

func TestPlannerService_CreatePlan_DuplicateError(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/create", func(w http.ResponseWriter, r *http.Request) {
		jsonErr(t, w, "Plan with this name and version already exists")
	})
	svc := newPlannerSvc(t, mux)

	_, err := svc.CreatePlan(context.Background(), models.CreatePlanRequest{Name: "dup"})
	require.Error(t, err)
	var apiErr *api.APIError
	require.True(t, errors.As(err, &apiErr))
	assert.Contains(t, apiErr.Body.Message, "already exists")
}

func TestPlannerService_DeletePlan_EscapesKeyAndSendsDeleteView(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		deleteView bool
		want       string
	}{
		{"keep view", false, "0"},
		{"delete view", true, "1"},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var gotEscaped, gotDeleteView, gotMethod string
			mux := http.NewServeMux()
			mux.HandleFunc("/api/v1/planning/plan/scylla-2026.2#3/delete", func(w http.ResponseWriter, r *http.Request) {
				gotMethod = r.Method
				gotEscaped = r.URL.EscapedPath()
				gotDeleteView = r.URL.Query().Get("deleteView")
				jsonOK(t, w, true)
			})
			svc := newPlannerSvc(t, mux)

			err := svc.DeletePlan(context.Background(), "scylla-2026.2#3", tc.deleteView)
			require.NoError(t, err)
			assert.Equal(t, "DELETE", gotMethod)
			// The '#' in the key is percent-escaped so it is not parsed as a fragment.
			assert.Contains(t, gotEscaped, "%23")
			assert.Equal(t, tc.want, gotDeleteView)
		})
	}
}

// --------------------------------------------------------------------------
// BuildTemplate (get --template)
// --------------------------------------------------------------------------

func TestPlannerService_BuildTemplate_BackResolvesNames(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{
		Name:            "2026.2 Longevity",
		Description:     "ga plan",
		ReleaseID:       "rel-1",
		Owner:           "u1",
		Participants:    []string{"u2"},
		TargetVersion:   "2026.2.0",
		Tests:           []string{"t1", "t2"},
		AssigneeMapping: map[string]string{"t3": "u2"},
	}

	tmpl, err := svc.BuildTemplate(context.Background(), plan)
	require.NoError(t, err)

	assert.Equal(t, "scylla-2026.2", tmpl.Release)
	assert.Equal(t, "alice", tmpl.Owner)
	// Unassigned tests are marked $owner; the assigned one keeps its assignee.
	assert.Equal(t, av(map[string]string{
		"Tier 1/longevity-100gb": "$owner",
		"Tier 1/longevity-200gb": "$owner",
		"Tier 2/longevity-100gb": "bob",
	}), tmpl.Assignments)
}

func TestPlannerService_BuildTemplate_SkipsUnknownTests(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{
		Name:      "p",
		ReleaseID: "rel-1",
		Owner:     "u1",
		Tests:     []string{"t1", "gone"}, // "gone" is not in the gridview
	}

	tmpl, err := svc.BuildTemplate(context.Background(), plan)
	require.NoError(t, err)
	// Tests no longer present in the gridview cannot be named and are skipped.
	assert.Equal(t, av(map[string]string{"Tier 1/longevity-100gb": "$owner"}), tmpl.Assignments)
}

// TestPlannerService_TemplateRoundTrip locks the get --template -> create path:
// BuildTemplate emits the group portion as the *display* (pretty) name, so
// BuildCreateRequest must map that display name back to the same group ID (and
// thus the same test UUIDs) when it builds the create payload.
func TestPlannerService_TemplateRoundTrip_DisplayNameMapsToGroupID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))
	ctx := context.Background()

	plan := models.ReleasePlan{
		Name:            "GA",
		ReleaseID:       "rel-1",
		Owner:           "u1",
		Tests:           []string{"t1", "t2"},          // tier1 (pretty "Tier 1")
		AssigneeMapping: map[string]string{"t3": "u2"}, // tier2 (pretty "Tier 2")
	}

	tmpl, err := svc.BuildTemplate(ctx, plan)
	require.NoError(t, err)
	// Sanity: the emitted refs use the group's display name, not its raw name.
	assert.Equal(t, "$owner", tmpl.Assignments["Tier 1/longevity-100gb"].Assignee)
	require.Contains(t, tmpl.Assignments, "Tier 2/longevity-100gb")

	// Feeding the template straight back must resolve the display names to the
	// original group/test UUIDs.
	req, warnings, err := svc.BuildCreateRequest(ctx, tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.ElementsMatch(t, []string{"t1", "t2", "t3"}, req.Tests)
	assert.Equal(t, map[string]string{"t3": "u2"}, req.Assignments)
	// Group names are never sent to the backend; they expand to test UUIDs.
	assert.Empty(t, req.Groups)
}

func TestPlannerService_ExpandGroup_ByDisplayName(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	// The group's display (pretty) name resolves to the same enabled tests as
	// its raw name.
	ids, err := svc.ExpandGroup(context.Background(), "rel-1", "Tier 1")
	require.NoError(t, err)
	assert.Equal(t, []string{"t1", "t2"}, ids)
}

// --------------------------------------------------------------------------
// Resolved plan view (default get / list output)
// --------------------------------------------------------------------------

func TestPlannerService_BuildResolvedPlan_ResolvesNames(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{
		ID:              "p1",
		Key:             "scylla-2026.2#1",
		Name:            "GA",
		Description:     "ga plan",
		ReleaseID:       "rel-1",
		Owner:           "u1",
		Participants:    []string{"u2"},
		TargetVersion:   "2026.2.0",
		Tests:           []string{"t1", "t3"},
		Groups:          []string{"g1"},
		AssigneeMapping: map[string]string{"t2": "u2"},
		Completed:       true,
	}

	rp, err := svc.BuildResolvedPlan(context.Background(), plan)
	require.NoError(t, err)

	assert.Equal(t, "scylla-2026.2#1", rp.Key)
	assert.Equal(t, "scylla-2026.2", rp.Release)
	assert.Equal(t, "alice", rp.Owner)
	assert.Equal(t, []string{"bob"}, rp.Participants)
	assert.Equal(t, []string{"Tier 1/longevity-100gb", "Tier 2/longevity-100gb"}, rp.Tests)
	assert.Equal(t, []string{"tier1"}, rp.Groups)
	assert.Equal(t, av(map[string]string{"Tier 1/longevity-200gb": "bob"}), rp.Assignments)
	// Identity/status fields are retained (unlike a template).
	assert.Equal(t, "p1", rp.ID)
	assert.True(t, rp.Completed)
}

func TestPlannerService_BuildResolvedPlan_UnknownRefsFallBackToUUID(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{
		ID:              "p2",
		ReleaseID:       "rel-1",
		Owner:           "u-missing",            // not in users
		Tests:           []string{"t1", "gone"}, // "gone" not in gridview
		AssigneeMapping: map[string]string{"gone": "u-missing"},
	}

	rp, err := svc.BuildResolvedPlan(context.Background(), plan)
	require.NoError(t, err)
	// Unknown references are kept verbatim (lossless), not dropped.
	assert.Equal(t, "u-missing", rp.Owner)
	assert.Equal(t, []string{"Tier 1/longevity-100gb", "gone"}, rp.Tests)
	assert.Equal(t, av(map[string]string{"gone": "u-missing"}), rp.Assignments)
}

func TestPlannerService_BuildResolvedPlan_UnknownReleaseFallsBack(t *testing.T) {
	t.Parallel()
	// gridview for the plan's release is served, but the releases list does not
	// contain it — the release name falls back to the raw id without failing.
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/releases", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, []models.Release{{ID: "other", Name: "scylla-2026.1"}})
	})
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{"u1": {ID: "u1", Username: "alice"}})
	})
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, gridviewFixture())
	})
	svc := newPlannerSvc(t, mux)

	rp, err := svc.BuildResolvedPlan(context.Background(),
		models.ReleasePlan{ReleaseID: "rel-1", Owner: "u1"})
	require.NoError(t, err)
	assert.Equal(t, "rel-1", rp.Release)
	assert.Equal(t, "alice", rp.Owner)
}

func TestPlannerService_BuildPlanSummaries_CountsAndNames(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plans := models.ReleasePlanList{
		{Key: "scylla-2026.2#1", ReleaseID: "rel-1", Owner: "u1",
			Tests: []string{"t1", "t2"}, Groups: []string{"g1"}, Participants: []string{"u2"}},
		{Key: "scylla-2026.2#2", ReleaseID: "rel-1", Owner: "u2"},
	}

	summaries, err := svc.BuildPlanSummaries(context.Background(), plans)
	require.NoError(t, err)
	require.Len(t, summaries, 2)
	assert.Equal(t, "alice", summaries[0].Owner)
	assert.Equal(t, "scylla-2026.2", summaries[0].Release)
	assert.Equal(t, 2, summaries[0].Tests)
	assert.Equal(t, 1, summaries[0].Groups)
	assert.Equal(t, 1, summaries[0].Participants)
	assert.Equal(t, "bob", summaries[1].Owner)
	assert.Equal(t, 0, summaries[1].Tests)
}

// --------------------------------------------------------------------------
// Update (diff-based, Phase 5)
// --------------------------------------------------------------------------

func strPtr(s string) *string { return &s }

func TestPlannerService_BuildUpdateRequest_ScalarOnly(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan,
		models.PlanUpdateSpec{Name: strPtr("renamed")})
	require.NoError(t, err)
	assert.Empty(t, warnings)

	assert.Equal(t, "p1", diff.ID)
	require.NotNil(t, diff.Name)
	assert.Equal(t, "renamed", *diff.Name)
	// A scalar-only edit must not produce any list/map deltas.
	assert.Nil(t, diff.TestsAdd)
	assert.Nil(t, diff.TestsRemove)
	assert.Nil(t, diff.GroupsAdd)
	assert.Nil(t, diff.GroupsRemove)
	assert.Nil(t, diff.ParticipantsAdd)
	assert.Nil(t, diff.AssigneeMappingSet)
	assert.Nil(t, diff.AssigneeMappingRemove)

	// The marshalled body carries only id + name.
	raw, err := json.Marshal(diff)
	require.NoError(t, err)
	s := string(raw)
	assert.Contains(t, s, `"name":"renamed"`)
	assert.NotContains(t, s, "tests_add")
	assert.NotContains(t, s, "assignee_mapping")
}

func TestPlannerService_BuildUpdateRequest_ResolvesOwner(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan,
		models.PlanUpdateSpec{Owner: strPtr("alice")})
	require.NoError(t, err)
	require.NotNil(t, diff.Owner)
	assert.Equal(t, "u1", *diff.Owner)
}

func TestPlannerService_BuildUpdateRequest_TestAddRemove(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsAdd:    []string{"tier1/longevity-200gb"},
		TestsRemove: []string{"scylla-2026.2/tier2/longevity-100gb"},
	})
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.Equal(t, []string{"t2"}, diff.TestsAdd)
	assert.Equal(t, []string{"t3"}, diff.TestsRemove)
	// Unrelated fields stay empty.
	assert.Nil(t, diff.GroupsRemove)
	assert.Nil(t, diff.ParticipantsAdd)
}

func TestPlannerService_BuildUpdateRequest_MissingTestWarns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsAdd: []string{"tier1/longevity-200gb", "tier1/does-not-exist"},
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"t2"}, diff.TestsAdd)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "does-not-exist")
}

func TestPlannerService_BuildUpdateRequest_AmbiguousTestAborts(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	_, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsAdd: []string{"longevity-100gb"}, // present in tier1 and tier2
	})
	require.Error(t, err)
	assert.True(t, errors.Is(err, services.ErrAmbiguousEntity))
}

func TestPlannerService_BuildUpdateRequest_AddGroupExpands(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		GroupsAdd: []string{"tier1"},
	})
	require.NoError(t, err)
	// tier1 expands to its enabled tests; no groups_add is ever sent.
	assert.Equal(t, []string{"t1", "t2"}, diff.TestsAdd)
	assert.Nil(t, diff.GroupsAdd)
}

func TestPlannerService_BuildUpdateRequest_RemoveGroup(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1"}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		GroupsRemove: []string{"tier2"},
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"g2"}, diff.GroupsRemove)
	assert.Nil(t, diff.TestsAdd)
}

func TestPlannerService_BuildUpdateRequest_MissingGroupAddWarns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A misspelled --add-group name warns and is skipped, so other deltas in the
	// same update still apply (rather than aborting the whole call).
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t1"}}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		GroupsAdd: []string{"tierX"},
		TestsAdd:  []string{"tier2/longevity-100gb"},
	})
	require.NoError(t, err)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "not in this release")
	// The valid test add is preserved.
	assert.Equal(t, []string{"t3"}, diff.TestsAdd)
}

func TestPlannerService_BuildUpdateRequest_MissingGroupRemoveWarns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A misspelled --remove-group name warns and is skipped, not fatal.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t1"}}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		GroupsRemove: []string{"tierX"},
	})
	require.NoError(t, err)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "not in this release")
	assert.Nil(t, diff.GroupsRemove)
}

func TestPlannerService_BuildUpdateRequest_AssignAddsParticipant(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// alice owns the plan; assigning bob to a test makes him a participant.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t1"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet: map[string]string{"tier1/longevity-200gb": "bob"},
	})
	require.NoError(t, err)
	assert.Equal(t, map[string]string{"t2": "u2"}, diff.AssigneeMappingSet)
	// The assigned test is not yet in the plan, so membership follows the
	// assignment — without tests_add the backend would drop the mapping.
	assert.Equal(t, []string{"t2"}, diff.TestsAdd)
	assert.Equal(t, []string{"u2"}, diff.ParticipantsAdd)
	assert.Empty(t, diff.ParticipantsRemove)
}

func TestPlannerService_BuildUpdateRequest_UnassignDropsParticipant(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// bob's only assignment (t2) cleared via $owner → dropped from participants.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests: []string{"t2"}, Participants: []string{"u2"},
		AssigneeMapping: map[string]string{"t2": "u2"},
	}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet: map[string]string{"tier1/longevity-200gb": "$owner"},
	})
	require.NoError(t, err)
	// $owner clears the assignee (test stays) and removes bob as participant.
	assert.Nil(t, diff.AssigneeMappingSet)
	assert.Equal(t, []string{"t2"}, diff.AssigneeMappingRemove)
	assert.Empty(t, diff.ParticipantsAdd)
	assert.Equal(t, []string{"u2"}, diff.ParticipantsRemove)
}

func TestPlannerService_BuildUpdateRequest_RemoveLastTestDropsParticipant(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// bob keeps another assigned test, so removing one keeps him a participant.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests: []string{"t1", "t2"}, Participants: []string{"u2"},
		AssigneeMapping: map[string]string{"t1": "u2", "t2": "u2"},
	}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsRemove: []string{"tier1/longevity-200gb"},
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"t2"}, diff.TestsRemove)
	assert.Empty(t, diff.ParticipantsRemove)
}

func TestPlannerService_BuildUpdateRequest_RejectsEmptyPlan(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t2"}}
	_, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsRemove: []string{"tier1/longevity-200gb"},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "at least one test")
}

func TestPlannerService_BuildUpdateRequest_RejectsEmptyPlanViaGroupRemoval(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A web-created plan can hold its membership as groups (no explicit tests).
	// Removing its last group empties it and must be refused. (Group removal
	// does not cascade to plan.tests server-side, so only a group-held plan can
	// be emptied this way.)
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Groups: []string{"g1"}}
	_, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		GroupsRemove: []string{"tier1"},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "at least one test")
}

func TestPlannerService_BuildUpdateRequest_RemoveLastTestKeepsGroup(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Removing the last explicit test is allowed while a group remains: the
	// plan still has membership, so the guard must not fire.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t2"}, Groups: []string{"g2"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		TestsRemove: []string{"tier1/longevity-200gb"},
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"t2"}, diff.TestsRemove)
}

func TestPlannerService_BuildUpdateRequest_AssignSetAndRemove(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t2", "t3"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet:    map[string]string{"tier1/longevity-200gb": "alice"},
		AssigneeMappingRemove: []string{"scylla-2026.2/tier2/longevity-100gb"},
	})
	require.NoError(t, err)
	// Entity key and user value are both resolved to UUIDs.
	assert.Equal(t, map[string]string{"t2": "u1"}, diff.AssigneeMappingSet)
	assert.Equal(t, []string{"t3"}, diff.AssigneeMappingRemove)
}

func TestPlannerService_BuildUpdateRequest_GroupAssignmentFansOut(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Tests: []string{"t1", "t2"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet: map[string]string{"tier1": "bob"},
	})
	require.NoError(t, err)
	// A group assignment fans out to each enabled member test.
	assert.Equal(t, map[string]string{"t1": "u2", "t2": "u2"}, diff.AssigneeMappingSet)
}

func TestPlannerService_BuildUpdateRequest_AssignmentsMergeReassigns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A template-style "assignments" file reassigns an existing test: t2 is
	// ensured present (already in the plan) and assigned to bob, who becomes a
	// participant. Tests not mentioned are left untouched.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t2"}}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		Assignments: av(map[string]string{"tier1/longevity-200gb": "bob"}),
	})
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.Equal(t, map[string]string{"t2": "u2"}, diff.AssigneeMappingSet)
	assert.Equal(t, []string{"t2"}, diff.TestsAdd)
	assert.Equal(t, []string{"u2"}, diff.ParticipantsAdd)
	assert.Empty(t, diff.ParticipantsRemove)
}

func TestPlannerService_BuildUpdateRequest_AssignmentsAddsNewTest(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A test named in "assignments" but not yet in the plan is added (membership
	// follows assignment) and assigned.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t1"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		Assignments: av(map[string]string{"tier2/longevity-100gb": "bob"}),
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"t3"}, diff.TestsAdd)
	assert.Equal(t, map[string]string{"t3": "u2"}, diff.AssigneeMappingSet)
	assert.Equal(t, []string{"u2"}, diff.ParticipantsAdd)
}

func TestPlannerService_BuildUpdateRequest_AssignmentsOwnerMarkerClears(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// $owner in a template "assignments" clears the assignee (test stays) and
	// drops the now-unassigned user from participants.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests: []string{"t2"}, Participants: []string{"u2"},
		AssigneeMapping: map[string]string{"t2": "u2"},
	}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		Assignments: av(map[string]string{"tier1/longevity-200gb": "$owner"}),
	})
	require.NoError(t, err)
	assert.Nil(t, diff.AssigneeMappingSet)
	assert.Equal(t, []string{"t2"}, diff.AssigneeMappingRemove)
	assert.Equal(t, []string{"u2"}, diff.ParticipantsRemove)
}

func TestPlannerService_BuildUpdateRequest_AssignmentsMissingWarns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A reference matching nothing is reported and skipped, not fatal.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t2"}}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		Assignments: av(map[string]string{"tier1/does-not-exist": "bob"}),
	})
	require.NoError(t, err)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "not in this release")
	assert.Empty(t, diff.AssigneeMappingSet)
}

func TestPlannerService_BuildUpdateRequest_AssignMissingWarns(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// --assign (AssigneeMappingSet) to a name matching nothing in the release is
	// reported and skipped, not fatal — mirroring template assignments.
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t2"}}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet: map[string]string{"tier1/does-not-exist": "bob"},
	})
	require.NoError(t, err)
	require.Len(t, warnings, 1)
	assert.Contains(t, warnings[0], "not in this release")
	assert.Empty(t, diff.AssigneeMappingSet)
	assert.Nil(t, diff.TestsAdd)
}

// the pretty-name "Tier", so a group-by-name assignment reference is ambiguous.
func ambiguousGroupMux(t *testing.T) *http.ServeMux {
	t.Helper()
	mux := releasesMux(t, nil)
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{"u2": {ID: "u2", Username: "bob"}})
	})
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.GridView{
			Groups: map[string]models.GridEntity{
				"g1": {ID: "g1", Name: "tier1", PrettyName: "Tier", Type: "group"},
				"g2": {ID: "g2", Name: "tier2", PrettyName: "Tier", Type: "group"},
			},
			Tests: map[string]models.GridEntity{
				"t1": {ID: "t1", Name: "longevity-a", GroupID: "g1", Group: "Tier",
					BuildSystemID: "scylla-2026.2/tier1/longevity-a", Enabled: true},
				"t2": {ID: "t2", Name: "longevity-b", GroupID: "g2", Group: "Tier",
					BuildSystemID: "scylla-2026.2/tier2/longevity-b", Enabled: true},
			},
		})
	})
	return mux
}

func TestPlannerService_BuildUpdateRequest_AmbiguousGroupAssignmentAborts(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, ambiguousGroupMux(t))

	// An assignment to a group name matching two groups must abort with a
	// disambiguation error, not be silently dropped as "not in release".
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t1"}}
	_, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		AssigneeMappingSet: map[string]string{"Tier": "bob"},
	})
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrAmbiguousEntity)
}

func TestPlannerService_BuildCreateRequest_AmbiguousGroupAssignmentAborts(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, ambiguousGroupMux(t))

	_, _, err := svc.BuildCreateRequest(context.Background(), models.PlanTemplate{
		Name:        "p",
		Release:     "scylla-2026.2",
		Owner:       "bob",
		Assignments: av(map[string]string{"Tier": "bob"}),
	})
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrAmbiguousEntity)
}

// TestPlannerService_ResolveEntityID_AmbiguousGroupPrefixSurfaces guards the
// group-qualified resolution path: when the "group/" prefix of a group-qualified
// test ref matches two groups, resolution must surface ErrAmbiguousEntity for
// disambiguation rather than falling through to bare-name matching and
// misreporting the test as simply not found.
func TestPlannerService_ResolveEntityID_AmbiguousGroupPrefixSurfaces(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, ambiguousGroupMux(t))

	_, err := svc.ResolveEntityID(context.Background(),
		"Tier/longevity-a", "rel-1", services.KindTest)
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrAmbiguousEntity)
	assert.NotErrorIs(t, err, services.ErrEntityNotFound)
}

func TestPlannerService_UpdatePlan_PostsDiff(t *testing.T) {
	t.Parallel()
	var gotBody models.PlanDiffRequest
	var gotMethod string
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/update", func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		require.NoError(t, json.NewDecoder(r.Body).Decode(&gotBody))
		jsonOK(t, w, true)
	})
	svc := newPlannerSvc(t, mux)

	name := "renamed"
	err := svc.UpdatePlan(context.Background(), models.PlanDiffRequest{ID: "p1", Name: &name})
	require.NoError(t, err)
	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "p1", gotBody.ID)
	require.NotNil(t, gotBody.Name)
	assert.Equal(t, "renamed", *gotBody.Name)
}

func TestPlannerService_UpdatePlan_BackendError(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/update", func(w http.ResponseWriter, r *http.Request) {
		jsonErr(t, w, "name and version already exist")
	})
	svc := newPlannerSvc(t, mux)

	err := svc.UpdatePlan(context.Background(), models.PlanDiffRequest{ID: "p1"})
	require.Error(t, err)
	var apiErr *api.APIError
	require.True(t, errors.As(err, &apiErr))
	assert.Contains(t, apiErr.Body.Message, "already exist")
}

// --------------------------------------------------------------------------
// Per-entity options (labels)
// --------------------------------------------------------------------------

func TestPlannerService_BuildCreateRequest_EmitsOptions(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Labels attach to the resolved entity UUID, including an unassigned test.
	tmpl := models.PlanTemplate{
		Name:    "labelled",
		Release: "scylla-2026.2",
		Owner:   "alice",
		Assignments: map[string]models.AssignmentValue{
			"tier1/longevity-200gb": {Assignee: "bob", Options: &models.EntityOptions{Labels: []string{"blocker"}}},
			"tier2/longevity-100gb": {Assignee: "$owner", Options: &models.EntityOptions{Labels: []string{"needs-triage"}}},
		},
	}

	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.Equal(t, map[string]models.EntityOptions{
		"t2": {Labels: []string{"blocker"}},
		"t3": {Labels: []string{"needs-triage"}},
	}, req.Options)
	// The $owner test still carries labels but no assignee.
	assert.Equal(t, map[string]string{"t2": "u2"}, req.Assignments)
}

func TestPlannerService_BuildCreateRequest_GroupLabelFansOut(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// A group entry's labels attach to each enabled member test (t1, t2).
	tmpl := models.PlanTemplate{
		Name:    "grouplabel",
		Release: "scylla-2026.2",
		Owner:   "alice",
		Assignments: map[string]models.AssignmentValue{
			"tier1": {Assignee: "bob", Options: &models.EntityOptions{Labels: []string{"smoke"}}},
		},
	}

	req, _, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Equal(t, map[string]models.EntityOptions{
		"t1": {Labels: []string{"smoke"}},
		"t2": {Labels: []string{"smoke"}},
	}, req.Options)
}

func TestPlannerService_BuildTemplate_IncludesLabels(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// The plan stores options as a JSON string keyed by entity UUID.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests:           []string{"t1", "t2"},
		AssigneeMapping: map[string]string{"t2": "u2"},
		Options:         `{"t1":{"labels":["needs-triage"]},"t2":{"labels":["blocker","smoke"]}}`,
	}

	tmpl, err := svc.BuildTemplate(context.Background(), plan)
	require.NoError(t, err)
	// Assigned test carries its labels; unassigned test keeps labels under $owner.
	assert.Equal(t, models.AssignmentValue{
		Assignee: "bob",
		Options:  &models.EntityOptions{Labels: []string{"blocker", "smoke"}},
	}, tmpl.Assignments["Tier 1/longevity-200gb"])
	assert.Equal(t, models.AssignmentValue{
		Assignee: "$owner",
		Options:  &models.EntityOptions{Labels: []string{"needs-triage"}},
	}, tmpl.Assignments["Tier 1/longevity-100gb"])
}

func TestPlannerService_BuildUpdateRequest_LabelAddMergesWithCurrent(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// t2 already has "blocker"; --label adds "smoke" → merged set is sent.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests:   []string{"t2"},
		Options: `{"t2":{"labels":["blocker"]}}`,
	}
	diff, warnings, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		LabelsAdd: map[string][]string{"tier1/longevity-200gb": {"smoke"}},
	})
	require.NoError(t, err)
	assert.Empty(t, warnings)
	assert.Equal(t, map[string]models.EntityOptions{
		"t2": {Labels: []string{"blocker", "smoke"}},
	}, diff.OptionsSet)
	assert.Nil(t, diff.OptionsRemove)
}

func TestPlannerService_BuildUpdateRequest_LabelAddAddsMembership(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Labelling a test not yet in the plan adds it (membership follows labels).
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t1"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		LabelsAdd: map[string][]string{"tier2/longevity-100gb": {"smoke"}},
	})
	require.NoError(t, err)
	assert.Equal(t, []string{"t3"}, diff.TestsAdd)
	assert.Equal(t, map[string]models.EntityOptions{"t3": {Labels: []string{"smoke"}}}, diff.OptionsSet)
}

func TestPlannerService_BuildUpdateRequest_UnlabelRemovesAllEmitsOptionsRemove(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// Removing the only label clears the entity's option bag via options_remove.
	plan := models.ReleasePlan{
		ID: "p1", ReleaseID: "rel-1", Owner: "u1",
		Tests:   []string{"t2"},
		Options: `{"t2":{"labels":["blocker"]}}`,
	}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		LabelsRemove: map[string][]string{"tier1/longevity-200gb": {"blocker"}},
	})
	require.NoError(t, err)
	assert.Nil(t, diff.OptionsSet)
	assert.Equal(t, []string{"t2"}, diff.OptionsRemove)
}

func TestPlannerService_BuildUpdateRequest_FileAssignmentsCarryLabels(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, resolveMux(t))

	// The template-style assignments map may carry labels (applied additively).
	plan := models.ReleasePlan{ID: "p1", ReleaseID: "rel-1", Owner: "u1", Tests: []string{"t2"}}
	diff, _, err := svc.BuildUpdateRequest(context.Background(), plan, models.PlanUpdateSpec{
		Assignments: map[string]models.AssignmentValue{
			"tier1/longevity-200gb": {Assignee: "bob", Options: &models.EntityOptions{Labels: []string{"smoke"}}},
		},
	})
	require.NoError(t, err)
	assert.Equal(t, map[string]string{"t2": "u2"}, diff.AssigneeMappingSet)
	assert.Equal(t, map[string]models.EntityOptions{"t2": {Labels: []string{"smoke"}}}, diff.OptionsSet)
}
