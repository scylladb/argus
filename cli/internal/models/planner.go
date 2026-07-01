package models

import (
	"sort"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------------------
// ReleasePlan – mirrors argus.backend.models.plan.ArgusReleasePlan
// ---------------------------------------------------------------------------

// ReleasePlan is a single release plan as returned by the planner endpoints.
//
// All UUID columns are serialised as strings by ArgusJSONEncoder; datetime
// columns are ISO-8601 strings. AssigneeMapping maps an entity UUID (test or
// group) to a user UUID.
//
// Key is the human-friendly "releaseName#planNumber" handle (e.g.
// "scylla-2026.2#3") added by the backend plan-keying change; plan operations
// accept it in place of a UUID.
type ReleasePlan struct {
	ID              string            `json:"id"`
	Key             string            `json:"key"`
	Name            string            `json:"name"`
	Description     string            `json:"description"`
	Owner           string            `json:"owner"`
	Participants    []string          `json:"participants"`
	TargetVersion   string            `json:"target_version"`
	AssigneeMapping map[string]string `json:"assignee_mapping"`
	ReleaseID       string            `json:"release_id"`
	Tests           []string          `json:"tests"`
	Groups          []string          `json:"groups"`
	ViewID          string            `json:"view_id"`
	CreatedFrom     string            `json:"created_from"`
	Completed       bool              `json:"completed"`
	CreationTime    string            `json:"creation_time"`
	LastUpdated     string            `json:"last_updated"`
	EndsAt          string            `json:"ends_at"`
}

// ReleasePlanList is the response payload for the plans-for-release endpoint.
type ReleasePlanList = []ReleasePlan

// Headers implements output.Tabular for ReleasePlan.
func (ReleasePlan) Headers() []string {
	return []string{"Key", "Name", "Target Version", "Owner", "Tests", "Groups", "Completed"}
}

// Rows implements output.Tabular for ReleasePlan.
func (p ReleasePlan) Rows() [][]string {
	return [][]string{{
		p.Key,
		p.Name,
		p.TargetVersion,
		p.Owner,
		strconv.Itoa(len(p.Tests)),
		strconv.Itoa(len(p.Groups)),
		strconv.FormatBool(p.Completed),
	}}
}

// ---------------------------------------------------------------------------
// Write request payloads
// ---------------------------------------------------------------------------

// CreatePlanRequest is the JSON body for POST /planning/plan/create.
//
// It mirrors CreatePlanPayload (planner_service.py): Assignments maps an
// entity UUID to a user UUID and is converted server-side into the plan's
// assignee_mapping. ViewID is optional — a view is auto-created when absent.
type CreatePlanRequest struct {
	Name          string            `json:"name"`
	Description   string            `json:"description"`
	Owner         string            `json:"owner"`
	Participants  []string          `json:"participants"`
	TargetVersion string            `json:"target_version"`
	ReleaseID     string            `json:"release_id"`
	Tests         []string          `json:"tests"`
	Groups        []string          `json:"groups"`
	Assignments   map[string]string `json:"assignments"`
	ViewID        string            `json:"view_id,omitempty"`
	CreatedFrom   string            `json:"created_from,omitempty"`
}

// PlanDiffRequest is the JSON body for POST /planning/plan/update.
//
// It mirrors PlanDiffPayload (planner_service.py): only changed scalar fields
// are sent (pointer fields, omitted when nil), and list/map mutations are
// expressed as add/remove deltas. The server applies removes before adds.
type PlanDiffRequest struct {
	ID string `json:"id"`

	// Scalar fields – only sent when changed (nil = no change).
	Name          *string `json:"name,omitempty"`
	Description   *string `json:"description,omitempty"`
	Owner         *string `json:"owner,omitempty"`
	TargetVersion *string `json:"target_version,omitempty"`
	Completed     *bool   `json:"completed,omitempty"`
	EndsAt        *string `json:"ends_at,omitempty"`
	ViewID        *string `json:"view_id,omitempty"`

	// List diffs.
	TestsAdd           []string `json:"tests_add,omitempty"`
	TestsRemove        []string `json:"tests_remove,omitempty"`
	GroupsAdd          []string `json:"groups_add,omitempty"`
	GroupsRemove       []string `json:"groups_remove,omitempty"`
	ParticipantsAdd    []string `json:"participants_add,omitempty"`
	ParticipantsRemove []string `json:"participants_remove,omitempty"`

	// Map diff for assignee_mapping.
	AssigneeMappingSet    map[string]string `json:"assignee_mapping_set,omitempty"`
	AssigneeMappingRemove []string          `json:"assignee_mapping_remove,omitempty"`
}

// ---------------------------------------------------------------------------
// Release / Gridview – name resolution and group expansion sources
// ---------------------------------------------------------------------------

// Release mirrors the subset of ArgusRelease returned by /api/v1/releases.
type Release struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	PrettyName string `json:"pretty_name"`
	Enabled    bool   `json:"enabled"`
}

// ReleaseList is the response payload for GET /api/v1/releases.
type ReleaseList = []Release

// User mirrors the subset of User returned by GET /api/v1/users (User.to_json).
type User struct {
	ID        string `json:"id"`
	Username  string `json:"username"`
	FullName  string `json:"full_name"`
	Email     string `json:"email"`
	PictureID string `json:"picture_id"`
}

// UsersMap is the response payload for GET /api/v1/users: a map keyed by the
// user's UUID string with the user object as the value.
type UsersMap = map[string]User

// GridEntity is a single test or group in a release's gridview (and the shape
// of index-mapped entities in copy-check "missing" lists).
//
// Group and Release are decorated *names* (strings) in the gridview, unlike
// the search endpoint where they are nested objects (see SearchHit).
type GridEntity struct {
	ID            string `json:"id"`
	Name          string `json:"name"`
	PrettyName    string `json:"pretty_name"`
	BuildSystemID string `json:"build_system_id"`
	GroupID       string `json:"group_id"`
	ReleaseID     string `json:"release_id"`
	Enabled       bool   `json:"enabled"`
	Type          string `json:"type"`
	Group         string `json:"group"`
	Release       string `json:"release"`
}

// GridView is the response payload for GET /planning/release/<id>/gridview.
//
// Tests and Groups are keyed by entity UUID and contain only enabled entities;
// TestByGroup maps a group UUID to its tests (including disabled ones) and is
// deliberately not used for enabled-only expansion.
type GridView struct {
	Tests       map[string]GridEntity   `json:"tests"`
	Groups      map[string]GridEntity   `json:"groups"`
	TestByGroup map[string][]GridEntity `json:"testByGroup"`
}

// ReleaseGrid is a release overview: every enabled test keyed by its
// group-qualified "group/test" reference (the same form `--assign`/`get`/`list`
// accept) and valued by its build_system_id. JSON output marshals the map
// directly; text output renders one sorted entry per line as
// `group/test: build_system_id` via String().
type ReleaseGrid map[string]string

// String renders the overview one entry per line, sorted by reference.
func (g ReleaseGrid) String() string {
	keys := make([]string, 0, len(g))
	for k := range g {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k)
		b.WriteString(": ")
		b.WriteString(g[k])
		b.WriteByte('\n')
	}
	return strings.TrimRight(b.String(), "\n")
}

// ---------------------------------------------------------------------------
// PlanTemplate – editable create-spec (default get / create --file schema)
// ---------------------------------------------------------------------------
// PlanTemplate is the release-independent, human-readable plan spec emitted by
// `planner get` (the default output) and consumed by `planner create --file`.
//
// Assignments is the single source of plan membership: it is keyed by a
// group-qualified "group/test" reference (or a group name, which fans out to
// its enabled tests) and valued by a username. The literal [OwnerMarker]
// ("$owner") denotes a test that belongs to the plan but is not assigned to a
// specific participant — it is placed in the plan's tests but left out of the
// assignee mapping. Owner is a username.
type PlanTemplate struct {
	Name          string            `json:"name"`
	Description   string            `json:"description,omitempty"`
	Release       string            `json:"release"`
	TargetVersion string            `json:"target_version,omitempty"`
	Owner         string            `json:"owner,omitempty"`
	Assignments   map[string]string `json:"assignments,omitempty"`
}

// OwnerMarker is the sentinel assignment value meaning "include this test in
// the plan but leave it unassigned (it implicitly belongs to the owner)".
const OwnerMarker = "$owner"

// PlanUpdateSpec is the name-based diff consumed by `planner update`. It is the
// schema for the `update --file` input and the intermediate that the `update`
// flags are overlaid onto; [services.PlannerService.BuildUpdateRequest]
// resolves it into the UUID-based [PlanDiffRequest] sent to the backend.
//
// Scalar pointer fields are sent only when set (nil = no change). List/map
// fields use the same add/remove delta shape as the wire payload, but every
// value is a human reference: tests as build_system_id or "group/test", groups
// by name, and AssigneeMappingSet keyed by a test/group reference with a
// username value ("$owner" clears the assignee while keeping the test).
// Participants are not edited directly: they are derived from the resulting
// assignments (assignees minus owner), so the CLI computes the participant
// deltas. Groups in GroupsAdd are expanded to their enabled tests at resolve
// time (never sent as groups_add).
//
// Assignments accepts the same "assignments" map that the [PlanTemplate] (the
// default `get`/`create` output) uses, applied as a merge/patch: each keyed
// test/group reference is ensured to be in the plan (added when missing) and
// assigned to the given username, or unassigned when the value is "$owner";
// tests not mentioned are left untouched. It is a convenience for round-tripping
// an edited template through `update --file`, and is folded into the test-add
// and assignee deltas at resolve time.
type PlanUpdateSpec struct {
	Name          *string `json:"name,omitempty"`
	Description   *string `json:"description,omitempty"`
	Owner         *string `json:"owner,omitempty"`
	TargetVersion *string `json:"target_version,omitempty"`
	Completed     *bool   `json:"completed,omitempty"`

	TestsAdd     []string `json:"tests_add,omitempty"`
	TestsRemove  []string `json:"tests_remove,omitempty"`
	GroupsAdd    []string `json:"groups_add,omitempty"`
	GroupsRemove []string `json:"groups_remove,omitempty"`

	AssigneeMappingSet    map[string]string `json:"assignee_mapping_set,omitempty"`
	AssigneeMappingRemove []string          `json:"assignee_mapping_remove,omitempty"`

	// Assignments is the template-style membership+assignment map, merged into
	// the deltas above (see the type doc). "$owner" clears an assignee.
	Assignments map[string]string `json:"assignments,omitempty"`
}

// ResolvedPlan is a human-readable view of a [ReleasePlan] with every UUID
// reference back-resolved to a name: release/owner/participant names, tests and
// assignment targets as group-qualified "group/test" strings, and groups as
// names. It is the output of `planner get --resolved` and the default `list`.
//
// Unlike [PlanTemplate] it retains the plan's identity and status (id, key,
// completed, timestamps) and never drops entities — a reference that cannot be
// resolved against the release gridview/users list falls back to its raw UUID
// rather than being omitted, so the output is lossless.
type ResolvedPlan struct {
	ID            string            `json:"id"`
	Key           string            `json:"key"`
	Name          string            `json:"name"`
	Description   string            `json:"description,omitempty"`
	Release       string            `json:"release"`
	TargetVersion string            `json:"target_version,omitempty"`
	Owner         string            `json:"owner"`
	Participants  []string          `json:"participants,omitempty"`
	Tests         []string          `json:"tests"`
	Groups        []string          `json:"groups,omitempty"`
	Assignments   map[string]string `json:"assignments,omitempty"`
	Completed     bool              `json:"completed"`
	ViewID        string            `json:"view_id,omitempty"`
	CreatedFrom   string            `json:"created_from,omitempty"`
	CreationTime  string            `json:"creation_time,omitempty"`
	LastUpdated   string            `json:"last_updated,omitempty"`
	EndsAt        string            `json:"ends_at,omitempty"`
}

// Headers implements output.Tabular for ResolvedPlan. Text output is a curated
// subset of fields; JSON output (via direct marshalling) still carries the full
// resolved plan.
func (ResolvedPlan) Headers() []string {
	return []string{"Key", "Name", "Description", "Release", "Target Version", "Owner", "Last Updated"}
}

// Rows implements output.Tabular for ResolvedPlan.
func (p ResolvedPlan) Rows() [][]string {
	return [][]string{{
		p.Key,
		p.Name,
		p.Description,
		p.Release,
		p.TargetVersion,
		p.Owner,
		p.LastUpdated,
	}}
}

// PlanSummary is the per-plan list view. Its JSON fields mirror the text-table
// columns exactly (test/group/participant references are reported as integer
// counts), so the `planner list` JSON and `--text` output carry the same data.
type PlanSummary struct {
	Key           string `json:"key"`
	Name          string `json:"name"`
	Description   string `json:"description"`
	Release       string `json:"release"`
	TargetVersion string `json:"target_version"`
	Owner         string `json:"owner"`
	Tests         int    `json:"tests"`
	Groups        int    `json:"groups"`
	Participants  int    `json:"participants"`
	LastUpdated   string `json:"last_updated"`
}

// Headers implements output.Tabular for PlanSummary.
func (PlanSummary) Headers() []string {
	return []string{"Key", "Name", "Description", "Release", "Target Version", "Owner", "Tests", "Groups", "Participants", "Last Updated"}
}

// Rows implements output.Tabular for PlanSummary.
func (p PlanSummary) Rows() [][]string {
	return [][]string{{
		p.Key,
		p.Name,
		p.Description,
		p.Release,
		p.TargetVersion,
		p.Owner,
		strconv.Itoa(p.Tests),
		strconv.Itoa(p.Groups),
		strconv.Itoa(p.Participants),
		p.LastUpdated,
	}}
}

// PlanSummaries is a slice of plan summaries rendered as one row per plan in
// text output, while JSON marshalling emits the full slice. It backs the
// default `planner list` output.
type PlanSummaries []PlanSummary

// Headers implements output.Tabular for PlanSummaries.
func (PlanSummaries) Headers() []string { return PlanSummary{}.Headers() }

// Rows implements output.Tabular for PlanSummaries.
func (ps PlanSummaries) Rows() [][]string {
	rows := make([][]string, 0, len(ps))
	for _, p := range ps {
		rows = append(rows, p.Rows()[0])
	}
	return rows
}

// ---------------------------------------------------------------------------
// SearchHit – /planning/search result
// ---------------------------------------------------------------------------

// SearchRef is the nested group/release object attached to a search hit.
// Unlike the gridview, the search endpoint returns these as objects, not
// decorated name strings.
type SearchRef struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	PrettyName string `json:"pretty_name"`
	Enabled    bool   `json:"enabled"`
}

// SearchHit is a single result of GET /planning/search. Type is one of
// "test", "group", "release", or "special" (the synthetic "Add all..." row,
// which is filtered out before display).
type SearchHit struct {
	ID            string     `json:"id"`
	Name          string     `json:"name"`
	PrettyName    string     `json:"pretty_name"`
	Type          string     `json:"type"`
	BuildSystemID string     `json:"build_system_id"`
	Enabled       bool       `json:"enabled"`
	Group         *SearchRef `json:"group"`
	Release       *SearchRef `json:"release"`
}

// SearchHitList is a slice of search hits (the displayed result set after the
// synthetic "Add all..." row is filtered out).
type SearchHitList = []SearchHit

// SearchResponse is the response payload for GET /planning/search. The backend
// wraps the hits in {hits, total}; Total counts the synthetic "Add all..." row
// too, so it is not used directly for display counts.
type SearchResponse struct {
	Hits  []SearchHit `json:"hits"`
	Total int         `json:"total"`
}

// Headers implements output.Tabular for SearchHit.
func (SearchHit) Headers() []string {
	return []string{"Type", "Name", "Build System Id", "Group", "Release"}
}

// Rows implements output.Tabular for SearchHit.
func (h SearchHit) Rows() [][]string {
	name := h.PrettyName
	if name == "" {
		name = h.Name
	}
	group := ""
	if h.Group != nil {
		group = h.Group.Name
	}
	release := ""
	if h.Release != nil {
		release = h.Release.Name
	}
	return [][]string{{h.Type, name, h.BuildSystemID, group, release}}
}
