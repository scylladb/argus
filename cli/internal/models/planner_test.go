package models_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// sampleReleasePlanJSON mirrors a single plan as serialised by the backend
// (UUIDs as strings, datetimes as ISO strings, snake_case keys).
const sampleReleasePlanJSON = `{
	"id": "7f3c1e90-0000-0000-0000-000000000001",
	"key": "scylla-2026.2#3",
	"name": "2026.2 Longevity",
	"description": "Longevity suite",
	"owner": "11111111-0000-0000-0000-000000000001",
	"participants": ["22222222-0000-0000-0000-000000000002"],
	"target_version": "2026.2.0~rc3",
	"assignee_mapping": {"c4d00000-0000-0000-0000-00000000007a": "11111111-0000-0000-0000-000000000001"},
	"release_id": "33333333-0000-0000-0000-000000000003",
	"tests": ["c4d00000-0000-0000-0000-00000000007a", "b7e20000-0000-0000-0000-000000000009"],
	"groups": ["9a1c0000-0000-0000-0000-000000000044"],
	"view_id": "44444444-0000-0000-0000-000000000004",
	"created_from": "",
	"completed": false,
	"creation_time": "2026-06-01T10:00:00.000000",
	"last_updated": "2026-06-02T11:00:00.000000",
	"ends_at": ""
}`

func TestReleasePlan_JSONRoundTrip(t *testing.T) {
	t.Parallel()

	var plan models.ReleasePlan
	require.NoError(t, json.Unmarshal([]byte(sampleReleasePlanJSON), &plan))

	assert.Equal(t, "7f3c1e90-0000-0000-0000-000000000001", plan.ID)
	assert.Equal(t, "scylla-2026.2#3", plan.Key)
	assert.Equal(t, "2026.2 Longevity", plan.Name)
	assert.Equal(t, "2026.2.0~rc3", plan.TargetVersion)
	assert.Len(t, plan.Tests, 2)
	assert.Len(t, plan.Groups, 1)
	assert.Equal(t, "11111111-0000-0000-0000-000000000001",
		plan.AssigneeMapping["c4d00000-0000-0000-0000-00000000007a"])
	assert.False(t, plan.Completed)

	// Marshal back and re-decode to confirm a stable round-trip.
	raw, err := json.Marshal(plan)
	require.NoError(t, err)
	var again models.ReleasePlan
	require.NoError(t, json.Unmarshal(raw, &again))
	assert.Equal(t, plan, again)
}

func TestReleasePlan_TabularShape(t *testing.T) {
	t.Parallel()

	var plan models.ReleasePlan
	require.NoError(t, json.Unmarshal([]byte(sampleReleasePlanJSON), &plan))

	headers := plan.Headers()
	rows := plan.Rows()
	require.Len(t, rows, 1)
	assert.Len(t, rows[0], len(headers), "row width must match header count")
	assert.Equal(t, []string{
		"scylla-2026.2#3", "2026.2 Longevity", "2026.2.0~rc3",
		"11111111-0000-0000-0000-000000000001", "2", "1", "false",
	}, rows[0])
}

func TestReleasePlanList_EmptySliceSerialisesAsArray(t *testing.T) {
	t.Parallel()

	list := []models.ReleasePlan{}
	raw, err := json.Marshal(list)
	require.NoError(t, err)
	assert.Equal(t, "[]", string(raw), "empty list must serialise as [] not null")
}

func TestPlanDiffRequest_OmitsUnsetOptionalScalars(t *testing.T) {
	t.Parallel()

	// Only the name changed; every other scalar/list/map must be absent.
	name := "renamed"
	diff := models.PlanDiffRequest{
		ID:   "7f3c1e90-0000-0000-0000-000000000001",
		Name: &name,
	}
	raw, err := json.Marshal(diff)
	require.NoError(t, err)
	s := string(raw)

	assert.Contains(t, s, `"id"`)
	assert.Contains(t, s, `"name":"renamed"`)

	// Unset optionals / empty deltas must not appear on the wire.
	for _, key := range []string{
		"description", "owner", "target_version", "completed", "ends_at", "view_id",
		"tests_add", "tests_remove", "groups_add", "groups_remove",
		"participants_add", "participants_remove",
		"assignee_mapping_set", "assignee_mapping_remove",
	} {
		assert.NotContainsf(t, s, `"`+key+`"`, "unset field %q must be omitted", key)
	}
}

func TestPlanDiffRequest_ListAndMapDeltas(t *testing.T) {
	t.Parallel()

	diff := models.PlanDiffRequest{
		ID:                 "id-1",
		TestsAdd:           []string{"a", "b"},
		GroupsRemove:       []string{"g"},
		AssigneeMappingSet: map[string]string{"a": "u"},
	}
	raw, err := json.Marshal(diff)
	require.NoError(t, err)
	s := string(raw)

	assert.Contains(t, s, `"tests_add":["a","b"]`)
	assert.Contains(t, s, `"groups_remove":["g"]`)
	assert.Contains(t, s, `"assignee_mapping_set":{"a":"u"}`)
	// tests_remove was left empty and must be omitted.
	assert.False(t, strings.Contains(s, `"tests_remove"`), "empty tests_remove must be omitted")
}

func TestPlanUpdateSpec_FileSchemaParses(t *testing.T) {
	t.Parallel()

	// The --file diff schema uses the wire field names but name-based values.
	const raw = `{
		"name": "2026.2 Longevity",
		"target_version": "2026.2.0~rc3",
		"tests_add": ["scylla-2026.2/longevity/longevity-100gb", "tier1/longevity-200gb"],
		"groups_remove": ["tier2"],
		"assignee_mapping_set": {"scylla-2026.2/longevity/longevity-100gb": "alice"},
		"assignee_mapping_remove": ["tier1/longevity-200gb"]
	}`

	var spec models.PlanUpdateSpec
	require.NoError(t, json.Unmarshal([]byte(raw), &spec))

	require.NotNil(t, spec.Name)
	assert.Equal(t, "2026.2 Longevity", *spec.Name)
	require.NotNil(t, spec.TargetVersion)
	assert.Equal(t, "2026.2.0~rc3", *spec.TargetVersion)
	// Unset scalars stay nil so they are never sent as "changes".
	assert.Nil(t, spec.Description)
	assert.Nil(t, spec.Owner)
	assert.Nil(t, spec.Completed)

	assert.Equal(t, []string{"scylla-2026.2/longevity/longevity-100gb", "tier1/longevity-200gb"}, spec.TestsAdd)
	assert.Equal(t, []string{"tier2"}, spec.GroupsRemove)
	assert.Equal(t, map[string]string{"scylla-2026.2/longevity/longevity-100gb": "alice"}, spec.AssigneeMappingSet)
	assert.Equal(t, []string{"tier1/longevity-200gb"}, spec.AssigneeMappingRemove)
}

func TestPlanUpdateSpec_OmitsUnsetFields(t *testing.T) {
	t.Parallel()

	name := "renamed"
	spec := models.PlanUpdateSpec{Name: &name}
	raw, err := json.Marshal(spec)
	require.NoError(t, err)
	s := string(raw)

	assert.Contains(t, s, `"name":"renamed"`)
	for _, key := range []string{
		"description", "owner", "target_version", "completed",
		"tests_add", "tests_remove", "groups_add", "groups_remove",
		"participants_add", "participants_remove",
		"assignee_mapping_set", "assignee_mapping_remove",
	} {
		assert.NotContainsf(t, s, `"`+key+`"`, "unset field %q must be omitted", key)
	}
}

func TestGridView_JSONRoundTrip(t *testing.T) {
	t.Parallel()

	const raw = `{
		"tests": {
			"c4d0": {"id": "c4d0", "name": "longevity-100gb", "pretty_name": "Longevity 100GB", "build_system_id": "scylla-2026.2/longevity/longevity-100gb", "group_id": "g1", "release_id": "r1", "enabled": true, "type": "test", "group": "longevity", "release": "scylla-2026.2"}
		},
		"groups": {
			"g1": {"id": "g1", "name": "longevity", "pretty_name": "Longevity", "build_system_id": "scylla-2026.2/longevity", "release_id": "r1", "enabled": true, "type": "group", "release": "scylla-2026.2"}
		},
		"testByGroup": {
			"g1": [{"id": "c4d0", "name": "longevity-100gb", "group_id": "g1", "enabled": true}]
		}
	}`

	var gv models.GridView
	require.NoError(t, json.Unmarshal([]byte(raw), &gv))

	test, ok := gv.Tests["c4d0"]
	require.True(t, ok)
	assert.Equal(t, "scylla-2026.2/longevity/longevity-100gb", test.BuildSystemID)
	assert.Equal(t, "longevity", test.Group) // decorated name string, not an object
	assert.Equal(t, "scylla-2026.2", test.Release)
	assert.Equal(t, "longevity", gv.Groups["g1"].Name)
	require.Len(t, gv.TestByGroup["g1"], 1)
}

func TestSearchHit_NestedRefsAndTabular(t *testing.T) {
	t.Parallel()

	const raw = `{
		"id": "c4d0",
		"name": "longevity-100gb",
		"pretty_name": "Longevity 100GB",
		"type": "test",
		"build_system_id": "scylla-2026.2/longevity/longevity-100gb",
		"enabled": true,
		"group": {"id": "g1", "name": "longevity", "pretty_name": "Longevity", "enabled": true},
		"release": {"id": "r1", "name": "scylla-2026.2", "pretty_name": "2026.2", "enabled": true}
	}`

	var hit models.SearchHit
	require.NoError(t, json.Unmarshal([]byte(raw), &hit))

	require.NotNil(t, hit.Group)
	require.NotNil(t, hit.Release)
	assert.Equal(t, "longevity", hit.Group.Name)
	assert.Equal(t, "scylla-2026.2", hit.Release.Name)

	rows := hit.Rows()
	require.Len(t, rows, 1)
	assert.Len(t, rows[0], len(hit.Headers()))
	// Prefers pretty_name for display, surfaces build_system_id + nested names.
	assert.Equal(t, []string{
		"test", "Longevity 100GB",
		"scylla-2026.2/longevity/longevity-100gb", "longevity", "scylla-2026.2",
	}, rows[0])
}

func TestSearchHit_NilRefsRenderEmpty(t *testing.T) {
	t.Parallel()

	hit := models.SearchHit{Type: "release", Name: "scylla-2026.2"}
	rows := hit.Rows()
	require.Len(t, rows, 1)
	assert.Equal(t, []string{"release", "scylla-2026.2", "", "", ""}, rows[0])
}

func TestCreatePlanRequest_OmitsOptionalEmptyFields(t *testing.T) {
	t.Parallel()

	req := models.CreatePlanRequest{
		Name:      "p",
		ReleaseID: "r1",
		Tests:     []string{"a"},
	}
	raw, err := json.Marshal(req)
	require.NoError(t, err)
	s := string(raw)

	assert.NotContains(t, s, `"view_id"`, "empty optional view_id must be omitted")
	assert.NotContains(t, s, `"created_from"`, "empty optional created_from must be omitted")
}

func TestAssignmentValue_UnmarshalAcceptsStringOrObject(t *testing.T) {
	t.Parallel()

	t.Run("bare string is the assignee (back-compat)", func(t *testing.T) {
		t.Parallel()
		var v models.AssignmentValue
		require.NoError(t, json.Unmarshal([]byte(`"bob"`), &v))
		assert.Equal(t, models.AssignmentValue{Assignee: "bob"}, v)
		assert.Nil(t, v.Labels())
	})

	t.Run("object with assignee and labels", func(t *testing.T) {
		t.Parallel()
		var v models.AssignmentValue
		require.NoError(t, json.Unmarshal([]byte(`{"assignee":"bob","options":{"labels":["a","b"]}}`), &v))
		assert.Equal(t, "bob", v.Assignee)
		assert.Equal(t, []string{"a", "b"}, v.Labels())
	})

	t.Run("object with labels only (unassigned)", func(t *testing.T) {
		t.Parallel()
		var v models.AssignmentValue
		require.NoError(t, json.Unmarshal([]byte(`{"options":{"labels":["x"]}}`), &v))
		assert.Empty(t, v.Assignee)
		assert.Equal(t, []string{"x"}, v.Labels())
	})

	t.Run("always marshals as an object", func(t *testing.T) {
		t.Parallel()
		raw, err := json.Marshal(models.AssignmentValue{Assignee: "bob"})
		require.NoError(t, err)
		assert.JSONEq(t, `{"assignee":"bob"}`, string(raw))
	})

	t.Run("round-trips a map keyed by reference", func(t *testing.T) {
		t.Parallel()
		var m map[string]models.AssignmentValue
		require.NoError(t, json.Unmarshal([]byte(`{"g/t1":"bob","g/t2":{"assignee":"$owner","options":{"labels":["l"]}}}`), &m))
		assert.Equal(t, "bob", m["g/t1"].Assignee)
		assert.Equal(t, "$owner", m["g/t2"].Assignee)
		assert.Equal(t, []string{"l"}, m["g/t2"].Labels())
	})
}

func TestParsePlanOptions(t *testing.T) {
	t.Parallel()

	t.Run("empty string yields an empty map", func(t *testing.T) {
		t.Parallel()
		got, err := models.ParsePlanOptions("")
		require.NoError(t, err)
		assert.Empty(t, got)
		assert.NotNil(t, got)
	})

	t.Run("parses entity-keyed options", func(t *testing.T) {
		t.Parallel()
		got, err := models.ParsePlanOptions(`{"uuid-1":{"labels":["a","b"]}}`)
		require.NoError(t, err)
		assert.Equal(t, map[string]models.EntityOptions{
			"uuid-1": {Labels: []string{"a", "b"}},
		}, got)
	})

	t.Run("errors on malformed JSON", func(t *testing.T) {
		t.Parallel()
		_, err := models.ParsePlanOptions(`{not json`)
		require.Error(t, err)
	})
}

func sampleResolvedPlan() models.ResolvedPlan {
	return models.ResolvedPlan{
		ID:            "p1",
		Key:           "scylla-2026.2#3",
		Name:          "2026.2 Longevity",
		Description:   "Longevity suite",
		Release:       "scylla-2026.2",
		TargetVersion: "2026.2.0~rc3",
		Owner:         "alice",
		Participants:  []string{"bob"},
		Tests:         []string{"Tier 1/longevity-100gb"},
		Groups:        []string{"tier1"},
		Assignments:   map[string]models.AssignmentValue{"Tier 1/longevity-200gb": {Assignee: "bob"}},
		Completed:     true,
		LastUpdated:   "2026-06-02T11:00:00.000000",
	}
}

func TestResolvedPlan_TabularShowsCuratedColumns(t *testing.T) {
	t.Parallel()

	plan := sampleResolvedPlan()
	headers := plan.Headers()
	assert.Equal(t, []string{
		"Key", "Name", "Description", "Release", "Target Version", "Owner", "Last Updated",
	}, headers)

	rows := plan.Rows()
	require.Len(t, rows, 1)
	assert.Len(t, rows[0], len(headers), "row width must match header count")
	assert.Equal(t, []string{
		"scylla-2026.2#3", "2026.2 Longevity", "Longevity suite",
		"scylla-2026.2", "2026.2.0~rc3", "alice", "2026-06-02T11:00:00.000000",
	}, rows[0])
}

func TestResolvedPlan_JSONKeepsFullDetail(t *testing.T) {
	t.Parallel()

	// Text output is curated, but JSON marshalling still carries every field —
	// including tests, groups, participants, and assignments.
	raw, err := json.Marshal(sampleResolvedPlan())
	require.NoError(t, err)
	s := string(raw)

	assert.Contains(t, s, `"tests":["Tier 1/longevity-100gb"]`)
	assert.Contains(t, s, `"groups":["tier1"]`)
	assert.Contains(t, s, `"participants":["bob"]`)
	assert.Contains(t, s, `"assignments":{"Tier 1/longevity-200gb":{"assignee":"bob"}}`)
	assert.Contains(t, s, `"id":"p1"`)
}

func TestPlanSummaries_TabularRowPerPlan(t *testing.T) {
	t.Parallel()

	plans := models.PlanSummaries{
		{Key: "scylla-2026.2#1", Name: "A", Owner: "alice", Tests: 3, Groups: 1, Participants: 2},
		{Key: "scylla-2026.2#2", Name: "B", Owner: "bob"},
	}
	assert.Equal(t, models.PlanSummary{}.Headers(), plans.Headers())

	rows := plans.Rows()
	require.Len(t, rows, 2)
	assert.Len(t, rows[0], len(plans.Headers()), "row width must match header count")
	assert.Equal(t, "scylla-2026.2#1", rows[0][0])
	assert.Equal(t, "alice", rows[0][5])
	assert.Equal(t, []string{"3", "1", "2"}, rows[0][6:9], "counts rendered as integers")
	assert.Equal(t, "scylla-2026.2#2", rows[1][0])
	assert.Equal(t, "bob", rows[1][5])
}

func TestPlanSummary_JSONMatchesColumns(t *testing.T) {
	t.Parallel()

	// JSON output must carry exactly the text-table columns, counts as integers.
	raw, err := json.Marshal(models.PlanSummary{
		Key: "scylla-2026.2#1", Name: "A", Release: "scylla-2026.2", Owner: "alice",
		Tests: 3, Groups: 1, Participants: 2,
	})
	require.NoError(t, err)

	var fields map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(raw, &fields))
	keys := make([]string, 0, len(fields))
	for k := range fields {
		keys = append(keys, k)
	}
	assert.ElementsMatch(t, []string{
		"key", "name", "description", "release", "target_version",
		"owner", "tests", "groups", "participants", "last_updated",
	}, keys)
	assert.JSONEq(t, `3`, string(fields["tests"]))
	assert.JSONEq(t, `1`, string(fields["groups"]))
	assert.JSONEq(t, `2`, string(fields["participants"]))
}

func TestReleaseGrid_StringSortedOnePerLine(t *testing.T) {
	t.Parallel()
	grid := models.ReleaseGrid{
		"tier2/b": "bsid-b",
		"tier1/a": "bsid-a",
	}
	assert.Equal(t, "tier1/a: bsid-a\ntier2/b: bsid-b", grid.String())
}

func TestReleaseGrid_MarshalsAsPlainMap(t *testing.T) {
	t.Parallel()
	grid := models.ReleaseGrid{"tier1/a": "bsid-a"}
	raw, err := json.Marshal(grid)
	require.NoError(t, err)
	assert.JSONEq(t, `{"tier1/a":"bsid-a"}`, string(raw))
}
