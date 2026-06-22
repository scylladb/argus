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
			"g1": {ID: "g1", Name: "tier1", PrettyName: "Tier 1", Type: "group"},
			"g2": {ID: "g2", Name: "tier2", PrettyName: "Tier 2", Type: "group"},
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

func TestPlannerService_ExpandGroup_EnabledOnly(t *testing.T) {
	t.Parallel()
	svc := newPlannerSvc(t, gridviewMux(t, nil))

	ids, err := svc.ExpandGroup(context.Background(), "rel-1", "tier1")
	require.NoError(t, err)
	// t1 + t2 are enabled in tier1; t4 is disabled and must be excluded.
	assert.Equal(t, []string{"t1", "t2"}, ids)
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
