package models_test

import (
	"encoding/json"
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// =========================================================================
// Widget registry
// =========================================================================

func TestKnownWidgetTypes_SortedAndComplete(t *testing.T) {
	types := models.KnownWidgetTypes()
	assert.Equal(t, []string{
		"githubIssues",
		"graphedStats",
		"graphs",
		"highlights",
		"nemesisStats",
		"pytestOverview",
		"releaseStats",
		"summary",
		"testDashboard",
	}, types, "the nine user-selectable widget types, sorted")
}

func TestIsKnownWidgetType(t *testing.T) {
	assert.True(t, models.IsKnownWidgetType("summary"))
	assert.True(t, models.IsKnownWidgetType("pytestOverview"))
	assert.False(t, models.IsKnownWidgetType("bogus"))
	// UNSUPPORTED is hidden in the UI and must not be selectable.
	assert.False(t, models.IsKnownWidgetType("UNSUPPORTED"))
	assert.False(t, models.IsKnownWidgetType(""))
}

func TestValidateWidgetType(t *testing.T) {
	// A recognised type validates cleanly.
	assert.NoError(t, models.ValidateWidgetType("summary"))
	assert.NoError(t, models.ValidateWidgetType("pytestOverview"))

	// An unknown type names the offender and lists the valid types.
	err := models.ValidateWidgetType("bogus")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "bogus")
	assert.Contains(t, err.Error(), "summary", "the error lists the valid types")

	// The hidden UNSUPPORTED placeholder is not a valid user selection.
	assert.Error(t, models.ValidateWidgetType("UNSUPPORTED"))
}

func TestDefaultWidgetSettings(t *testing.T) {
	// A scalar-defaulted type.
	summary := models.DefaultWidgetSettings("summary")
	assert.Equal(t, map[string]any{"packageName": "scylla-server"}, summary)

	// A settings-less type yields an empty (non-nil) object.
	graphs := models.DefaultWidgetSettings("graphs")
	assert.NotNil(t, graphs)
	assert.Empty(t, graphs)

	// An unknown type yields nil.
	assert.Nil(t, models.DefaultWidgetSettings("bogus"))

	// The returned map is a copy: mutating it must not corrupt the registry.
	summary["packageName"] = "mutated"
	assert.Equal(t, "scylla-server", models.DefaultWidgetSettings("summary")["packageName"])
}

func TestNewWidgetWithDefaults(t *testing.T) {
	w := models.NewWidgetWithDefaults("pytestOverview", 3)
	assert.Equal(t, 3, w.Position)
	assert.Equal(t, "pytestOverview", w.Type)
	assert.Equal(t, []string{}, w.Filter, "a fresh widget filters nothing")

	var settings map[string]any
	require.NoError(t, json.Unmarshal(w.Settings, &settings))
	assert.Equal(t, false, settings["collapsed"])
	statuses, ok := settings["enabledStatuses"].([]any)
	require.True(t, ok)
	assert.Len(t, statuses, 10, "all pytest statuses enabled by default")

	// An unknown type still yields a widget with an empty settings object
	// (the service validates and rejects the type separately).
	unknown := models.NewWidgetWithDefaults("bogus", 1)
	assert.Equal(t, "bogus", unknown.Type)
	assert.JSONEq(t, "{}", string(unknown.Settings))
}

func TestAllWidgetTypeInfos(t *testing.T) {
	infos := models.AllWidgetTypeInfos()
	require.Len(t, infos, 9)

	// Sorted by type, with friendly names and default-settings JSON.
	assert.Equal(t, "githubIssues", infos[0].Type)
	assert.Equal(t, "Github Scoped Issue View", infos[0].Name)

	// Every row carries valid JSON settings and a friendly name.
	for _, info := range infos {
		assert.NotEmpty(t, info.Name, "widget %q must have a friendly name", info.Type)
		var m map[string]any
		assert.NoError(t, json.Unmarshal([]byte(info.Settings), &m),
			"widget %q settings must be valid JSON", info.Type)
	}

	// Tabular contract.
	assert.Equal(t, []string{"Type", "Name", "Default Settings"}, infos.Headers())
	assert.Len(t, infos.Rows(), 9)
	assert.Equal(t, "githubIssues", infos.Rows()[0][0])
}
