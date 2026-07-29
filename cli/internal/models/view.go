package models

import (
	"encoding/json"
	"strconv"
)

// ---------------------------------------------------------------------------
// View – mirrors argus.backend.models.web.ArgusUserView
// ---------------------------------------------------------------------------

// View is a single user view as returned by the view endpoints (create/get/all).
//
// All UUID columns are serialised as strings and datetime columns as ISO-8601
// strings by the backend JSON encoder. Tests/ReleaseIDs/GroupIDs hold the
// view's resolved membership (the backend expands a release/group item into its
// member test ids). WidgetSettings is a JSON array (stored as a Text column) of
// widget objects — see [ViewWidget].
type View struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	DisplayName    string   `json:"display_name"`
	Description    string   `json:"description"`
	UserID         string   `json:"user_id"`
	PlanID         string   `json:"plan_id"`
	Tests          []string `json:"tests"`
	ReleaseIDs     []string `json:"release_ids"`
	GroupIDs       []string `json:"group_ids"`
	Created        string   `json:"created"`
	LastUpdated    string   `json:"last_updated"`
	WidgetSettings string   `json:"widget_settings"`
}

// ViewList is the response payload for GET /api/v1/views/all.
type ViewList = []View

// ResolvedView is the payload of GET /api/v1/views/<id>/resolve: the raw view
// plus an Items list that carries each membership entity's build_system_id
// (tests/groups) or name (releases), used to reverse-map the view's UUID
// membership back to human references.
type ResolvedView struct {
	View
	Items []ResolvedViewItem `json:"items"`
}

// ResolvedViewItem is a single entity in a [ResolvedView]. Type is one of
// "test", "group", or "release". BuildSystemID is the release-qualified path for
// tests and groups; releases are identified by Name instead.
type ResolvedViewItem struct {
	ID            string `json:"id"`
	Type          string `json:"type"`
	Name          string `json:"name"`
	PrettyName    string `json:"pretty_name"`
	BuildSystemID string `json:"build_system_id"`
	GroupID       string `json:"group_id"`
	ReleaseID     string `json:"release_id"`
	Group         string `json:"group"`
	Release       string `json:"release"`
	Enabled       bool   `json:"enabled"`
}

// ---------------------------------------------------------------------------
// ViewTemplate – editable get/create/update schema
// ---------------------------------------------------------------------------

// ViewTemplate is the release-independent, human-readable view spec emitted by
// `view get` (the default output) and consumed by `view create --file` /
// `view update --file`.
//
// Items is a list of entity references expressed as build_system_id paths: a
// single segment ("scylla-2026.2") is a release, "release/group" a group, and
// "release/group/test" a test. Widgets carry the same reference form in their
// Filter lists. PlanKey is the plan's human handle ("releaseName#planNumber"),
// surfaced read-only by `get`; it is ignored by create and update (a plan-backed
// view keeps its plan_id because update omits it). URL is the web address that
// opens the view in Argus, also read-only.
type ViewTemplate struct {
	ID          string       `json:"id,omitempty"`
	Name        string       `json:"name"`
	DisplayName string       `json:"display_name,omitempty"`
	Description string       `json:"description,omitempty"`
	PlanKey     string       `json:"plan_key,omitempty"`
	URL         string       `json:"url,omitempty"`
	Items       []string     `json:"items"`
	Widgets     []ViewWidget `json:"widgets"`
}

// ViewWidget is a single dashboard widget. It is both the template form (Filter
// holds build_system_id references) and the stored form inside a view's
// widget_settings JSON array (Filter holds bare entity UUIDs); the view service
// maps between the two. Settings is an opaque per-widget object passed through
// verbatim.
type ViewWidget struct {
	Position int             `json:"position"`
	Type     string          `json:"type"`
	Settings json.RawMessage `json:"settings,omitempty"`
	Filter   []string        `json:"filter"`
}

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

// ViewCreateRequest is the POST /api/v1/views/create body. Note the backend's
// naming asymmetry versus update: create takes camelCase displayName and a
// settings string (the widget_settings JSON array). Items are "type:uuid"
// strings ("test:<uuid>", "group:<uuid>", "release:<uuid>").
type ViewCreateRequest struct {
	Name        string   `json:"name"`
	DisplayName string   `json:"displayName,omitempty"`
	Description string   `json:"description,omitempty"`
	Items       []string `json:"items"`
	Settings    string   `json:"settings"`
}

// ViewUpdateRequest is the POST /api/v1/views/update body: the target viewId and
// the nested updateData the backend applies. Items is a full replacement of the
// view's membership; the backend rebuilds tests/release_ids/group_ids from it.
type ViewUpdateRequest struct {
	ViewID     string         `json:"viewId"`
	UpdateData ViewUpdateData `json:"updateData"`
}

// ViewUpdateData is the nested update payload. Every key present is applied
// (full replace), so all fields are always sent from the current-or-file
// template. plan_id is deliberately absent: omitting it preserves a plan-backed
// view's link. Items is required by the backend (it has no default).
type ViewUpdateData struct {
	Name           string   `json:"name"`
	DisplayName    string   `json:"display_name"`
	Description    string   `json:"description"`
	Items          []string `json:"items"`
	WidgetSettings string   `json:"widget_settings"`
}

// ---------------------------------------------------------------------------
// ViewSummary – per-view list output
// ---------------------------------------------------------------------------

// ViewSummary is the per-view list row. Tests is the resolved membership size
// (an integer count), keeping the text table and JSON output aligned. PlanKey is
// the plan's human handle ("releaseName#planNumber"), resolved from the view's
// plan_id, or empty for a view with no plan. URL is the web address that opens
// the view in Argus.
type ViewSummary struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	DisplayName string `json:"display_name"`
	Description string `json:"description"`
	Owner       string `json:"owner"`
	PlanKey     string `json:"plan_key"`
	Tests       int    `json:"tests"`
	LastUpdated string `json:"last_updated"`
	URL         string `json:"url"`
}

// Headers implements output.Tabular for ViewSummary.
func (ViewSummary) Headers() []string {
	return []string{"Id", "Name", "Display Name", "Description", "Owner", "Plan", "Tests", "Last Updated", "URL"}
}

// Rows implements output.Tabular for ViewSummary.
func (v ViewSummary) Rows() [][]string {
	return [][]string{{
		v.ID,
		v.Name,
		v.DisplayName,
		v.Description,
		v.Owner,
		v.PlanKey,
		strconv.Itoa(v.Tests),
		v.LastUpdated,
		v.URL,
	}}
}

// ViewSummaries is a slice of view summaries rendered as one row per view in
// text output, while JSON marshalling emits the full slice. It backs the
// default `view list` output.
type ViewSummaries []ViewSummary

// Headers implements output.Tabular for ViewSummaries.
func (ViewSummaries) Headers() []string { return ViewSummary{}.Headers() }

// Rows implements output.Tabular for ViewSummaries.
func (vs ViewSummaries) Rows() [][]string {
	rows := make([][]string, 0, len(vs))
	for _, v := range vs {
		rows = append(rows, v.Rows()[0])
	}
	return rows
}
