package models

import "strconv"

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

// CopyPlanRequest is the JSON body for POST /planning/plan/copy.
//
// It mirrors CopyPlanPayload (planner_service.py): Plan is the source plan
// (with name/version/description/owner overrides applied), Replacements maps a
// missing source-entity UUID to a substitute target-entity UUID.
type CopyPlanRequest struct {
	Plan              ReleasePlan       `json:"plan"`
	KeepParticipants  bool              `json:"keepParticipants"`
	Replacements      map[string]string `json:"replacements"`
	TargetReleaseID   string            `json:"targetReleaseId"`
	TargetReleaseName string            `json:"targetReleaseName"`
}

// ---------------------------------------------------------------------------
// Copy eligibility check response
// ---------------------------------------------------------------------------

// CopyCheckResponse is the payload of GET /planning/plan/<id>/copy/check.
//
// Status is "passed" or "failed"; Missing lists entities that have no
// equivalent in the target release (by build_system_id remap).
type CopyCheckResponse struct {
	Status          string          `json:"status"`
	TargetRelease   Release         `json:"targetRelease"`
	OriginalRelease Release         `json:"originalRelease"`
	Missing         MissingEntities `json:"missing"`
}

// MissingEntities groups the missing tests and groups of a copy eligibility check.
type MissingEntities struct {
	Tests  []GridEntity `json:"tests"`
	Groups []GridEntity `json:"groups"`
}

// ---------------------------------------------------------------------------
// Release / Gridview – name resolution and group expansion sources
// ---------------------------------------------------------------------------

// Release mirrors the subset of ArgusRelease returned by /api/v1/releases and
// the copy-check endpoint.
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

// ---------------------------------------------------------------------------
// PlanTemplate – editable create-spec (get --template / create --file schema)
// ---------------------------------------------------------------------------
// PlanTemplate is the release-independent, human-readable plan spec emitted by
// `planner get --template` and consumed by `planner create --file`.
//
// Tests are group-qualified "group/test" strings, Owner/Participants are
// usernames, and Assignments are keyed by "group/test".
type PlanTemplate struct {
	Name          string            `json:"name"`
	Description   string            `json:"description,omitempty"`
	Release       string            `json:"release"`
	TargetVersion string            `json:"target_version,omitempty"`
	Owner         string            `json:"owner,omitempty"`
	Participants  []string          `json:"participants,omitempty"`
	Tests         []string          `json:"tests"`
	Assignments   map[string]string `json:"assignments,omitempty"`
}

// ResolvedPlan is a human-readable view of a [ReleasePlan] with every UUID
// reference back-resolved to a name: release/owner/participant names, tests and
// assignment targets as group-qualified "group/test" strings, and groups as
// names. It is the default (non-`--template`) output of `planner get`/`list`.
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

// ResolvedPlans is a slice of resolved plans rendered as one row per plan in
// text output, while JSON marshalling emits the full slice. It backs the
// default `planner list` output.
type ResolvedPlans []ResolvedPlan

// Headers implements output.Tabular for ResolvedPlans.
func (ResolvedPlans) Headers() []string { return ResolvedPlan{}.Headers() }

// Rows implements output.Tabular for ResolvedPlans.
func (ps ResolvedPlans) Rows() [][]string {
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
