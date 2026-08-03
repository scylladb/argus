package models

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

// ---------------------------------------------------------------------------
// Widget registry – mirrors frontend/Common/ViewTypes.js (WIDGET_TYPES)
// ---------------------------------------------------------------------------
//
// The registry lets the CLI validate a widget's type and populate the default
// settings for that type exactly like the dashboard editor does
// (frontend/Views/ViewWidget.svelte populateWidgetSettings), so a view created
// or updated from the CLI stores complete, renderable widgets.

// widgetFriendlyNames maps each widget type to its human-readable name (the
// friendlyName in WIDGET_TYPES). The UNSUPPORTED placeholder is intentionally
// omitted: it is hidden in the UI and never user-selectable.
var widgetFriendlyNames = map[string]string{
	"testDashboard":  "Test Dashboard",
	"releaseStats":   "Stat bar",
	"githubIssues":   "Github Scoped Issue View",
	"highlights":     "Highlights and action items for the view",
	"summary":        "Per version summary for specified release",
	"graphs":         "Graphs Views",
	"nemesisStats":   "Nemesis stats",
	"graphedStats":   "Graphed Stats",
	"pytestOverview": "Pytest Stats",
}

// pytestStatuses is the full ordered set of pytest statuses (frontend
// TestStatus.js PytestStatus), the default value of pytestOverview's
// enabledStatuses setting.
var pytestStatuses = []any{
	"passed", "failure", "skipped", "error", "xfailed", "xpass",
	"passed & error", "failure & error", "skipped & error", "error & error",
}

// highlightsGroupItems is the default action-item list a highlights widget seeds
// (frontend WIDGET_TYPES.highlights.defaultGroupItems).
var highlightsGroupItems = []any{
	"dtest - release",
	"dtest - debug",
	"dtest - release with raft",
	"dtest - release with topology changes",
	"SCT investigations",
	"Drivers",
	"SBOM",
	"Azure image publish",
	"Release Notes",
}

// widgetDefaults maps each widget type to its default settings object, mirroring
// the per-type settingDefinitions defaults in WIDGET_TYPES. Types with no
// settings (graphs, nemesisStats) map to an empty object.
var widgetDefaults = map[string]map[string]any{
	"testDashboard": {
		"targetVersion":            false,
		"versionsIncludeNoVersion": true,
		"flatView":                 false,
		"productVersion":           "",
	},
	"releaseStats": {
		"horizontal":           false,
		"displayExtendedStats": false,
		"hiddenStatuses":       []any{},
	},
	"githubIssues": {
		"submitDisabled":   true,
		"aggregateByIssue": true,
	},
	"highlights": {
		"index":             0,
		"defaultGroupItems": highlightsGroupItems,
	},
	"summary": {
		"packageName": "scylla-server",
	},
	"graphs":       {},
	"nemesisStats": {},
	"graphedStats": {
		"testFilters": []any{},
	},
	"pytestOverview": {
		"collapsed":       false,
		"enabledStatuses": pytestStatuses,
	},
}

// KnownWidgetTypes returns the sorted list of valid widget type identifiers.
func KnownWidgetTypes() []string {
	types := make([]string, 0, len(widgetDefaults))
	for t := range widgetDefaults {
		types = append(types, t)
	}
	sort.Strings(types)
	return types
}

// IsKnownWidgetType reports whether t is a recognised widget type.
func IsKnownWidgetType(t string) bool {
	_, ok := widgetDefaults[t]
	return ok
}

// ValidateWidgetType returns nil when t is a recognised widget type, or an error
// naming the offending type and listing the valid ones. It is used to reject
// user-supplied widget types (--widget flags and --file specs) up front; widgets
// read back from a stored view are intentionally not validated so a view built
// with a newer widget catalog than this CLI knows can still be edited.
func ValidateWidgetType(t string) error {
	if IsKnownWidgetType(t) {
		return nil
	}
	return fmt.Errorf("unknown widget type %q; valid types: %s", t, strings.Join(KnownWidgetTypes(), ", "))
}

// DefaultWidgetSettings returns a fresh copy of the default settings map for a
// widget type, or nil when the type is unknown.
func DefaultWidgetSettings(t string) map[string]any {
	defs, ok := widgetDefaults[t]
	if !ok {
		return nil
	}
	out := make(map[string]any, len(defs))
	for k, v := range defs {
		out[k] = v
	}
	return out
}

// NewWidgetWithDefaults builds a widget of the given type pre-populated with its
// default settings, the given position, and an empty filter. The type is assumed
// valid (validate with [IsKnownWidgetType] first); an unknown type yields an
// empty settings object.
func NewWidgetWithDefaults(widgetType string, position int) ViewWidget {
	settings := DefaultWidgetSettings(widgetType)
	if settings == nil {
		settings = map[string]any{}
	}
	raw, _ := json.Marshal(settings)
	return ViewWidget{
		Position: position,
		Type:     widgetType,
		Settings: raw,
		Filter:   []string{},
	}
}

// ---------------------------------------------------------------------------
// WidgetTypeInfo – `view widgets` discovery output
// ---------------------------------------------------------------------------

// WidgetTypeInfo describes a single widget type for the `view widgets` command:
// its identifier, friendly name, and default settings JSON.
type WidgetTypeInfo struct {
	Type     string `json:"type"`
	Name     string `json:"name"`
	Settings string `json:"settings"`
}

// WidgetTypeInfos is the full registry rendered as one row per widget type.
type WidgetTypeInfos []WidgetTypeInfo

// AllWidgetTypeInfos returns the registry as a sorted slice of [WidgetTypeInfo].
func AllWidgetTypeInfos() WidgetTypeInfos {
	types := KnownWidgetTypes()
	out := make(WidgetTypeInfos, 0, len(types))
	for _, t := range types {
		raw, _ := json.Marshal(widgetDefaults[t])
		out = append(out, WidgetTypeInfo{
			Type:     t,
			Name:     widgetFriendlyNames[t],
			Settings: string(raw),
		})
	}
	return out
}

// Headers implements output.Tabular for WidgetTypeInfos.
func (WidgetTypeInfos) Headers() []string {
	return []string{"Type", "Name", "Default Settings"}
}

// Rows implements output.Tabular for WidgetTypeInfos.
func (w WidgetTypeInfos) Rows() [][]string {
	rows := make([][]string, 0, len(w))
	for _, info := range w {
		rows = append(rows, []string{info.Type, info.Name, info.Settings})
	}
	return rows
}
