package services_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newViewSvc spins up an httptest server for mux and returns a ViewService
// wired to it with caching disabled.
func newViewSvc(t *testing.T, mux *http.ServeMux) *services.ViewService {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))
	return services.NewViewService(client, ca)
}

// gridviewFixtureRel2 is a second release's structure, used to prove global
// reference resolution spans releases.
func gridviewFixtureRel2() models.GridView {
	return models.GridView{
		Groups: map[string]models.GridEntity{
			"g3": {ID: "g3", Name: "tier1", PrettyName: "Tier 1", Type: "group",
				BuildSystemID: "scylla-2026.1/tier1"},
		},
		Tests: map[string]models.GridEntity{
			"t5": {ID: "t5", Name: "longevity-500gb", GroupID: "g3", Group: "Tier 1",
				BuildSystemID: "scylla-2026.1/tier1/longevity-500gb", Enabled: true},
		},
	}
}

// registerResolveEndpoints serves the releases, users, and per-release gridview
// endpoints the view service needs for reference resolution.
func registerResolveEndpoints(t *testing.T, mux *http.ServeMux) {
	t.Helper()
	mux.HandleFunc("/api/v1/releases", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, []models.Release{
			{ID: "rel-1", Name: "scylla-2026.2", Enabled: true},
			{ID: "rel-2", Name: "scylla-2026.1", Enabled: true},
		})
	})
	mux.HandleFunc("/api/v1/users", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.UsersMap{
			"u1": {ID: "u1", Username: "alice"},
			"u2": {ID: "u2", Username: "bob"},
		})
	})
	mux.HandleFunc("/api/v1/planning/release/rel-1/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, gridviewFixture())
	})
	mux.HandleFunc("/api/v1/planning/release/rel-2/gridview", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, gridviewFixtureRel2())
	})
}

// --------------------------------------------------------------------------
// ResolveGlobalRef
// --------------------------------------------------------------------------

func TestPlannerService_ResolveGlobalRef(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newPlannerSvc(t, mux)
	ctx := context.Background()

	cases := []struct {
		name     string
		ref      string
		wantID   string
		wantKind services.EntityKind
	}{
		{"release", "scylla-2026.2", "rel-1", services.KindRelease},
		{"group", "scylla-2026.2/tier1", "g1", services.KindGroup},
		{"test", "scylla-2026.2/tier1/longevity-100gb", "t1", services.KindTest},
		{"cross-release test", "scylla-2026.1/tier1/longevity-500gb", "t5", services.KindTest},
		{"cross-release group", "scylla-2026.1/tier1", "g3", services.KindGroup},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			id, kind, err := svc.ResolveGlobalRef(ctx, tc.ref)
			require.NoError(t, err)
			assert.Equal(t, tc.wantID, id)
			assert.Equal(t, tc.wantKind, kind)
		})
	}
}

func TestPlannerService_ResolveGlobalRef_Miss(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newPlannerSvc(t, mux)

	_, _, err := svc.ResolveGlobalRef(context.Background(), "scylla-2026.2/tier1/does-not-exist")
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrEntityNotFound)
}

func TestPlannerService_UsernameByID(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newPlannerSvc(t, mux)
	ctx := context.Background()

	name, err := svc.UsernameByID(ctx, "u1")
	require.NoError(t, err)
	assert.Equal(t, "alice", name)

	// Unknown id falls back to the raw id.
	name, err = svc.UsernameByID(ctx, "u-unknown")
	require.NoError(t, err)
	assert.Equal(t, "u-unknown", name)
}

func TestPlannerService_PlanKeyByID(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/planning/plan/plan-xyz/get", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ReleasePlan{ID: "plan-xyz", Key: "scylla-2026.2#3"})
	})
	svc := newPlannerSvc(t, mux)
	ctx := context.Background()

	// A known plan resolves to its human key.
	key, err := svc.PlanKeyByID(ctx, "plan-xyz")
	require.NoError(t, err)
	assert.Equal(t, "scylla-2026.2#3", key)

	// An empty id yields an empty key (no lookup).
	key, err = svc.PlanKeyByID(ctx, "")
	require.NoError(t, err)
	assert.Empty(t, key)

	// A stale/unknown plan_id falls back to the raw id instead of erroring.
	key, err = svc.PlanKeyByID(ctx, "does-not-exist")
	require.NoError(t, err)
	assert.Equal(t, "does-not-exist", key)
}

// --------------------------------------------------------------------------
// List / summaries
// --------------------------------------------------------------------------

func TestViewService_ListViews(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	mux.HandleFunc("/api/v1/planning/plan/plan-xyz/get", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ReleasePlan{ID: "plan-xyz", Key: "scylla-2026.2#3"})
	})
	mux.HandleFunc("/api/v1/views/all", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "GET", r.Method)
		assert.Empty(t, r.URL.Query().Get("userId"), "no --user means no userId filter")
		jsonOK(t, w, models.ViewList{
			{ID: "v1", Name: "dash-a", DisplayName: "Dash A", UserID: "u1", PlanID: "plan-xyz", Tests: []string{"t1", "t2"}},
			{ID: "v2", Name: "dash-b", DisplayName: "Dash B", UserID: "u2", Tests: []string{"t3"}},
		})
	})
	svc := newViewSvc(t, mux)
	ctx := context.Background()

	views, err := svc.ListViews(ctx, "")
	require.NoError(t, err)
	require.Len(t, views, 2)

	summaries, err := svc.BuildSummaries(ctx, views)
	require.NoError(t, err)
	require.Len(t, summaries, 2)
	assert.Equal(t, "alice", summaries[0].Owner)
	assert.Equal(t, 2, summaries[0].Tests)
	assert.Equal(t, "scylla-2026.2#3", summaries[0].PlanKey, "plan_id resolves to plan key")
	assert.True(t, strings.HasSuffix(summaries[0].URL, "/view/dash-a"), "URL opens the view by name, got %q", summaries[0].URL)
	assert.Equal(t, "bob", summaries[1].Owner)
	assert.Equal(t, 1, summaries[1].Tests)
	assert.Empty(t, summaries[1].PlanKey, "a view with no plan has an empty plan key")
}

func TestViewService_ListViews_FilteredByUser(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	mux.HandleFunc("/api/v1/views/all", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "u1", r.URL.Query().Get("userId"), "username resolves to userId")
		jsonOK(t, w, models.ViewList{{ID: "v1", Name: "dash-a", UserID: "u1"}})
	})
	svc := newViewSvc(t, mux)

	views, err := svc.ListViews(context.Background(), "alice")
	require.NoError(t, err)
	require.Len(t, views, 1)
}

// --------------------------------------------------------------------------
// Get / addressing
// --------------------------------------------------------------------------

func TestViewService_GetView_ByUUID(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/get", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "7f3c1e90-0000-0000-0000-000000000001", r.URL.Query().Get("viewId"))
		jsonOK(t, w, models.View{ID: "7f3c1e90-0000-0000-0000-000000000001", Name: "dash-a"})
	})
	// A UUID addresses directly: /views/all must NOT be consulted.
	mux.HandleFunc("/api/v1/views/all", func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("unexpected call to /views/all for a UUID reference")
	})
	svc := newViewSvc(t, mux)

	view, err := svc.GetView(context.Background(), "7f3c1e90-0000-0000-0000-000000000001")
	require.NoError(t, err)
	assert.Equal(t, "dash-a", view.Name)
}

func TestViewService_GetView_ByName(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/all", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ViewList{
			{ID: "v1", Name: "dash-a"},
			{ID: "v2", Name: "dash-b"},
		})
	})
	mux.HandleFunc("/api/v1/views/get", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "v2", r.URL.Query().Get("viewId"))
		jsonOK(t, w, models.View{ID: "v2", Name: "dash-b"})
	})
	svc := newViewSvc(t, mux)

	view, err := svc.GetView(context.Background(), "dash-b")
	require.NoError(t, err)
	assert.Equal(t, "v2", view.ID)
}

func TestViewService_GetView_ByName_NoMatch(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/all", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ViewList{{ID: "v1", Name: "dash-a"}})
	})
	svc := newViewSvc(t, mux)

	_, err := svc.GetView(context.Background(), "nope")
	require.Error(t, err)
}

// --------------------------------------------------------------------------
// View → template round-trip (reverse mapping)
// --------------------------------------------------------------------------

func TestViewService_ViewToTemplate(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	mux.HandleFunc("/api/v1/planning/plan/plan-xyz/get", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ReleasePlan{ID: "plan-xyz", Key: "scylla-2026.2#3"})
	})
	mux.HandleFunc("/api/v1/views/v1/resolve", func(w http.ResponseWriter, r *http.Request) {
		jsonOK(t, w, models.ResolvedView{
			View: models.View{ID: "v1", Name: "dash-a"},
			Items: []models.ResolvedViewItem{
				{ID: "rel-1", Type: "release", Name: "scylla-2026.2"},
				{ID: "g1", Type: "group", BuildSystemID: "scylla-2026.2/tier1"},
				{ID: "t1", Type: "test", BuildSystemID: "scylla-2026.2/tier1/longevity-100gb"},
			},
		})
	})
	svc := newViewSvc(t, mux)

	view := models.View{
		ID:          "v1",
		Name:        "dash-a",
		DisplayName: "Dash A",
		PlanID:      "plan-xyz",
		WidgetSettings: `[{"position":0,"type":"summary","settings":{"foo":"bar"},` +
			`"filter":["t1","unmapped-uuid"]}]`,
	}
	tmpl, warnings, err := svc.ViewToTemplate(context.Background(), view)
	require.NoError(t, err)

	// Items reverse-mapped to references (build_system_id / release name), sorted.
	assert.Equal(t, []string{
		"scylla-2026.2",
		"scylla-2026.2/tier1",
		"scylla-2026.2/tier1/longevity-100gb",
	}, tmpl.Items)

	// plan_id resolved to its human-friendly plan key.
	assert.Equal(t, "scylla-2026.2#3", tmpl.PlanKey)

	// URL opens the view by name via the backend /view/<name> route.
	assert.True(t, strings.HasSuffix(tmpl.URL, "/view/dash-a"), "got %q", tmpl.URL)

	// Widget filter: mapped uuid → ref, unmapped uuid kept verbatim (+warning).
	require.Len(t, tmpl.Widgets, 1)
	assert.Equal(t, []string{"scylla-2026.2/tier1/longevity-100gb", "unmapped-uuid"}, tmpl.Widgets[0].Filter)
	assert.NotEmpty(t, warnings, "an unmapped filter uuid should be reported")
}

// --------------------------------------------------------------------------
// Create request shaping
// --------------------------------------------------------------------------

func TestViewService_BuildCreateRequest(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	tmpl := models.ViewTemplate{
		Name:        "dash-a",
		DisplayName: "Dash A",
		Items:       []string{"scylla-2026.2/tier1/longevity-100gb", "scylla-2026.2/tier2"},
		Widgets: []models.ViewWidget{
			{Position: 0, Type: "summary", Filter: []string{"scylla-2026.2/tier2"}},
		},
	}
	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)

	// Items become "type:uuid" strings, order preserved.
	assert.Equal(t, []string{"test:t1", "group:g2"}, req.Items)

	// A widget filter referencing a view item resolves to that item's bare UUID.
	assert.Contains(t, req.Settings, `"filter":["g2"]`)

	// The create payload uses camelCase displayName and a settings string.
	raw, err := json.Marshal(req)
	require.NoError(t, err)
	var m map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(raw, &m))
	assert.Contains(t, m, "displayName")
	assert.Contains(t, m, "settings")
	assert.NotContains(t, m, "widget_settings")
	assert.NotContains(t, m, "updateData")
}

func TestViewService_BuildCreateRequest_UnresolvedItemWarns(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	tmpl := models.ViewTemplate{
		Name:  "dash-a",
		Items: []string{"scylla-2026.2/tier1/longevity-100gb", "scylla-2026.2/tier1/ghost"},
	}
	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Equal(t, []string{"test:t1"}, req.Items, "ghost item omitted")
	assert.NotEmpty(t, warnings)
}

func TestViewService_BuildCreateRequest_NoWidgets(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	req, _, err := svc.BuildCreateRequest(context.Background(), models.ViewTemplate{Name: "empty"})
	require.NoError(t, err)
	assert.Equal(t, "[]", req.Settings, "no widgets defaults to an empty JSON array")
	assert.Equal(t, []string{}, req.Items)
}

func TestViewService_BuildCreateRequest_NameRequired(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	_, _, err := svc.BuildCreateRequest(context.Background(), models.ViewTemplate{})
	require.Error(t, err)
}

func TestViewService_BuildCreateRequest_WidgetDefaultsFilledAndReflowed(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	// Two widgets: the first carries a partial override, the second a bare
	// type from --widget (position 0). Both must land with full defaults and
	// 1-based positions.
	tmpl := models.ViewTemplate{
		Name: "dash-a",
		Widgets: []models.ViewWidget{
			{Position: 0, Type: "summary", Settings: json.RawMessage(`{"packageName":"scylla-enterprise"}`)},
			models.NewWidgetWithDefaults("releaseStats", 0),
		},
	}
	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.Empty(t, warnings)

	var widgets []map[string]json.RawMessage
	require.NoError(t, json.Unmarshal([]byte(req.Settings), &widgets))
	require.Len(t, widgets, 2)

	// Positions reflow to a 1-based sequence regardless of the input.
	assert.JSONEq(t, "1", string(widgets[0]["position"]))
	assert.JSONEq(t, "2", string(widgets[1]["position"]))

	// The caller's override is preserved; other default keys are added.
	var s0 map[string]any
	require.NoError(t, json.Unmarshal(widgets[0]["settings"], &s0))
	assert.Equal(t, "scylla-enterprise", s0["packageName"], "explicit setting preserved")

	// The bare --widget keeps its full defaults untouched.
	var s1 map[string]any
	require.NoError(t, json.Unmarshal(widgets[1]["settings"], &s1))
	assert.Equal(t, false, s1["horizontal"])
	assert.Equal(t, false, s1["displayExtendedStats"])
	assert.Contains(t, s1, "hiddenStatuses")
}

func TestViewService_BuildCreateRequest_UnknownWidgetTypePassesThrough(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	// The service no longer rejects an unrecognised type: it stores the widget
	// verbatim (no defaults are known) and warns, so a view built with a newer
	// widget catalog than this CLI knows still round-trips. Strict rejection of
	// user-supplied types lives at the command boundary instead.
	tmpl := models.ViewTemplate{
		Name: "dash-a",
		Widgets: []models.ViewWidget{
			{Type: "futureWidget", Settings: json.RawMessage(`{"keep":"me"}`)},
		},
	}
	req, warnings, err := svc.BuildCreateRequest(context.Background(), tmpl)
	require.NoError(t, err)
	assert.NotEmpty(t, warnings, "an unrecognised widget type is reported")

	var widgets []map[string]json.RawMessage
	require.NoError(t, json.Unmarshal([]byte(req.Settings), &widgets))
	require.Len(t, widgets, 1)
	assert.JSONEq(t, `"futureWidget"`, string(widgets[0]["type"]), "type kept verbatim")
	// Settings are untouched: no default keys are injected for an unknown type.
	assert.JSONEq(t, `{"keep":"me"}`, string(widgets[0]["settings"]))
}

// --------------------------------------------------------------------------
// Update request shaping
// --------------------------------------------------------------------------

func TestViewService_BuildUpdateRequest(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	tmpl := models.ViewTemplate{
		Name:        "dash-a",
		DisplayName: "Dash A",
		Description: "desc",
		PlanKey:     "scylla-2026.2#3", // must NOT be forwarded
		Items:       []string{"scylla-2026.2/tier1/longevity-100gb"},
	}
	req, _, err := svc.BuildUpdateRequest(context.Background(), "v1", tmpl)
	require.NoError(t, err)
	assert.Equal(t, "v1", req.ViewID)
	assert.Equal(t, []string{"test:t1"}, req.UpdateData.Items)
	assert.Equal(t, "[]", req.UpdateData.WidgetSettings)

	// Payload nests under updateData with snake_case keys and no plan_id.
	raw, err := json.Marshal(req)
	require.NoError(t, err)
	assert.Contains(t, string(raw), `"viewId"`)
	assert.Contains(t, string(raw), `"updateData"`)

	var m struct {
		UpdateData map[string]json.RawMessage `json:"updateData"`
	}
	require.NoError(t, json.Unmarshal(raw, &m))
	assert.Contains(t, m.UpdateData, "widget_settings")
	assert.Contains(t, m.UpdateData, "display_name")
	assert.Contains(t, m.UpdateData, "items")
	assert.NotContains(t, m.UpdateData, "plan_id", "plan_id must be omitted to preserve it")
}

// A widget filter must stay a subset of the view's items. When an update drops
// an item, any widget filter that still references it is pruned (with a warning)
// so the stored filter never dangles.
func TestViewService_BuildUpdateRequest_DropsFilterForRemovedItem(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	registerResolveEndpoints(t, mux)
	svc := newViewSvc(t, mux)

	// The view keeps item t1 but drops the tier2 group; a widget still filters on
	// both the surviving item and the removed one.
	tmpl := models.ViewTemplate{
		Name:  "dash-a",
		Items: []string{"scylla-2026.2/tier1/longevity-100gb"},
		Widgets: []models.ViewWidget{
			{Position: 0, Type: "summary", Filter: []string{
				"scylla-2026.2/tier1/longevity-100gb", // kept — still an item
				"scylla-2026.2/tier2",                 // dropped — no longer an item
			}},
		},
	}
	req, warnings, err := svc.BuildUpdateRequest(context.Background(), "v1", tmpl)
	require.NoError(t, err)

	assert.Equal(t, []string{"test:t1"}, req.UpdateData.Items)
	// Only the surviving item's UUID remains in the filter.
	assert.Contains(t, req.UpdateData.WidgetSettings, `"filter":["t1"]`)
	assert.NotContains(t, req.UpdateData.WidgetSettings, "g2")
	assert.NotEmpty(t, warnings, "dropping the removed item's filter should warn")
}

// --------------------------------------------------------------------------
// Write endpoints (round-trip)
// --------------------------------------------------------------------------

func TestViewService_CreateView(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/create", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "POST", r.Method)
		var body map[string]json.RawMessage
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		assert.Contains(t, body, "settings")
		jsonOK(t, w, models.View{ID: "v-new", Name: "dash-a"})
	})
	svc := newViewSvc(t, mux)

	view, err := svc.CreateView(context.Background(), models.ViewCreateRequest{
		Name: "dash-a", Items: []string{}, Settings: "[]",
	})
	require.NoError(t, err)
	assert.Equal(t, "v-new", view.ID)
}

func TestViewService_UpdateView(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/update", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "POST", r.Method)
		var body map[string]json.RawMessage
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		assert.Contains(t, body, "viewId")
		assert.Contains(t, body, "updateData")
		jsonOK(t, w, true)
	})
	svc := newViewSvc(t, mux)

	err := svc.UpdateView(context.Background(), models.ViewUpdateRequest{
		ViewID: "v1",
		UpdateData: models.ViewUpdateData{
			Name: "dash-a", Items: []string{}, WidgetSettings: "[]",
		},
	})
	require.NoError(t, err)
}

func TestViewService_DeleteView(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/views/delete", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "POST", r.Method)
		var body map[string]string
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		assert.Equal(t, "v1", body["viewId"])
		jsonOK(t, w, true)
	})
	svc := newViewSvc(t, mux)

	require.NoError(t, svc.DeleteView(context.Background(), "v1"))
}
