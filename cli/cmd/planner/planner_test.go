package planner

import (
	"testing"

	"github.com/scylladb/argus/cli/internal/models"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newSubCmd registers the planner sub-commands on a throwaway parent and
// returns the one named name, mirroring how cmd/planner.go wires them.
func newSubCmd(t *testing.T, name string) *cobra.Command {
	t.Helper()
	parent := &cobra.Command{Use: "planner"}
	Register(parent)
	for _, c := range parent.Commands() {
		if c.Name() == name {
			return c
		}
	}
	require.FailNowf(t, "sub-command not registered", "%q", name)
	return nil
}

func TestRegister_WiresAllSubCommands(t *testing.T) {
	t.Parallel()
	parent := &cobra.Command{Use: "planner"}
	Register(parent)

	names := map[string]bool{}
	for _, c := range parent.Commands() {
		names[c.Name()] = true
	}
	for _, want := range []string{"list", "get", "create", "update", "delete", "overview"} {
		assert.Truef(t, names[want], "expected %q sub-command", want)
	}
}

func TestGet_ResolvedFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	assert.NotNil(t, cmd.Flags().Lookup("resolved"))
}

func TestGet_RawFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	assert.NotNil(t, cmd.Flags().Lookup("raw"))
}

func TestGet_ResolvedAndRawAreMutuallyExclusive(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	require.NoError(t, cmd.ParseFlags([]string{"--resolved", "--raw"}))
	err := cmd.ValidateFlagGroups()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "none of the others can be")
}

func TestList_RawFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "list")
	assert.NotNil(t, cmd.Flags().Lookup("raw"))
}

func TestOverview_FlagsRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "overview")
	release := cmd.Flags().Lookup("release")
	require.NotNil(t, release)
	assert.Equal(t, "r", release.Shorthand)
}

func TestDelete_FlagsRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "delete")
	assert.NotNil(t, cmd.Flags().Lookup("no-delete-view"))
	assert.NotNil(t, cmd.Flags().Lookup("yes"))
	planID := cmd.Flags().Lookup("plan-id")
	require.NotNil(t, planID)
	assert.Equal(t, "p", planID.Shorthand)
}

func TestParseAssignments(t *testing.T) {
	t.Parallel()

	t.Run("merges over base and supports / in entity", func(t *testing.T) {
		t.Parallel()
		base := map[string]models.AssignmentValue{
			"tier1/a": {Assignee: "alice"},
			"keep":    {Assignee: "carol"},
		}
		got, err := parseAssignments([]string{"tier1/a=bob", "tier2/b=dave"}, base)
		require.NoError(t, err)
		assert.Equal(t, map[string]models.AssignmentValue{
			"tier1/a": {Assignee: "bob"},  // flag overrides base
			"tier2/b": {Assignee: "dave"}, // new entry
			"keep":    {Assignee: "carol"},
		}, got)
		// Base is not mutated.
		assert.Equal(t, "alice", base["tier1/a"].Assignee)
	})

	t.Run("preserves existing labels when setting assignee", func(t *testing.T) {
		t.Parallel()
		base := map[string]models.AssignmentValue{
			"tier1/a": {Options: &models.EntityOptions{Labels: []string{"smoke"}}},
		}
		got, err := parseAssignments([]string{"tier1/a=bob"}, base)
		require.NoError(t, err)
		assert.Equal(t, models.AssignmentValue{
			Assignee: "bob",
			Options:  &models.EntityOptions{Labels: []string{"smoke"}},
		}, got["tier1/a"])
	})

	t.Run("rejects malformed values", func(t *testing.T) {
		t.Parallel()
		for _, bad := range []string{"noequals", "=bob", "entity=", "  =  "} {
			_, err := parseAssignments([]string{bad}, nil)
			require.Errorf(t, err, "expected error for %q", bad)
		}
	})
}

func TestParseLabels(t *testing.T) {
	t.Parallel()

	t.Run("appends labels preserving assignee and dedupes", func(t *testing.T) {
		t.Parallel()
		base := map[string]models.AssignmentValue{"tier1/a": {Assignee: "bob"}}
		got, err := parseLabels([]string{"tier1/a=smoke", "tier1/a=smoke", "tier1/a=blocker"}, base)
		require.NoError(t, err)
		assert.Equal(t, models.AssignmentValue{
			Assignee: "bob",
			Options:  &models.EntityOptions{Labels: []string{"smoke", "blocker"}},
		}, got["tier1/a"])
		// Base is not mutated.
		assert.Nil(t, base["tier1/a"].Options)
	})

	t.Run("labels an unassigned entity", func(t *testing.T) {
		t.Parallel()
		got, err := parseLabels([]string{"tier1/a=needs-triage"}, nil)
		require.NoError(t, err)
		assert.Equal(t, models.AssignmentValue{
			Options: &models.EntityOptions{Labels: []string{"needs-triage"}},
		}, got["tier1/a"])
	})

	t.Run("rejects malformed values", func(t *testing.T) {
		t.Parallel()
		for _, bad := range []string{"noequals", "=lbl", "entity=", "  =  "} {
			_, err := parseLabels([]string{bad}, nil)
			require.Errorf(t, err, "expected error for %q", bad)
		}
	})
}

func TestOverlayFlags_FlagOverFilePrecedence(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "create")
	require.NoError(t, cmd.Flags().Set("name", "FlagName"))
	require.NoError(t, cmd.Flags().Set("assign", "x=u2"))
	require.NoError(t, cmd.Flags().Set("assign", "y=u3"))

	tmpl := models.PlanTemplate{
		Name:        "FileName",
		Release:     "scylla-2026.2",
		Assignments: map[string]models.AssignmentValue{"x": {Assignee: "u1"}},
	}

	require.NoError(t, overlayFlags(cmd, &tmpl))

	// Scalar flag overrides the file value.
	assert.Equal(t, "FlagName", tmpl.Name)
	// Release is untouched (flag not set).
	assert.Equal(t, "scylla-2026.2", tmpl.Release)
	// Assignment x overridden, y added.
	assert.Equal(t, map[string]models.AssignmentValue{
		"x": {Assignee: "u2"},
		"y": {Assignee: "u3"},
	}, tmpl.Assignments)
}

func TestOverlayFlags_UnsetScalarsKeepFileValues(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "create")

	tmpl := models.PlanTemplate{Name: "FileName", Owner: "alice"}
	require.NoError(t, overlayFlags(cmd, &tmpl))
	assert.Equal(t, "FileName", tmpl.Name)
	assert.Equal(t, "alice", tmpl.Owner)
}

func TestUpdate_FlagsRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "update")
	for _, name := range []string{
		"name", "description", "owner", "target-version", "completed",
		"add-test", "remove-test", "add-group", "remove-group",
		"assign", "unassign", "label", "unlabel", "file",
	} {
		assert.NotNilf(t, cmd.Flags().Lookup(name), "expected --%s flag", name)
	}
	// Participants are derived from assignments — no manual participant flags.
	assert.Nil(t, cmd.Flags().Lookup("add-participant"))
	assert.Nil(t, cmd.Flags().Lookup("remove-participant"))
	planID := cmd.Flags().Lookup("plan-id")
	require.NotNil(t, planID)
	assert.Equal(t, "p", planID.Shorthand)
}

func TestOverlayUpdateFlags_OnlySetScalarsAndAugmentedCollections(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "update")
	require.NoError(t, cmd.Flags().Set("name", "FlagName"))
	require.NoError(t, cmd.Flags().Set("completed", "true"))
	require.NoError(t, cmd.Flags().Set("add-test", "tier1/b"))
	require.NoError(t, cmd.Flags().Set("remove-group", "tier2"))
	require.NoError(t, cmd.Flags().Set("unassign", "tier1/c"))
	require.NoError(t, cmd.Flags().Set("assign", "x=u2"))
	require.NoError(t, cmd.Flags().Set("label", "tier1/a=smoke"))
	require.NoError(t, cmd.Flags().Set("unlabel", "tier1/d=stale"))

	// Pre-populate from a file: name is overridden, description is preserved,
	// and collections are augmented.
	desc := "from file"
	spec := models.PlanUpdateSpec{
		Name:               strPtrT("FileName"),
		Description:        &desc,
		TestsAdd:           []string{"tier1/a"},
		AssigneeMappingSet: map[string]string{"x": "u1"},
		LabelsAdd:          map[string][]string{"tier1/a": {"blocker"}},
	}

	require.NoError(t, overlayUpdateFlags(cmd, &spec))

	// Scalar flag overrides the file value.
	require.NotNil(t, spec.Name)
	assert.Equal(t, "FlagName", *spec.Name)
	// Unset scalar keeps the file value; untouched scalars stay nil.
	require.NotNil(t, spec.Description)
	assert.Equal(t, "from file", *spec.Description)
	assert.Nil(t, spec.Owner)
	require.NotNil(t, spec.Completed)
	assert.True(t, *spec.Completed)
	// Collections augment the file collections.
	assert.Equal(t, []string{"tier1/a", "tier1/b"}, spec.TestsAdd)
	assert.Equal(t, []string{"tier2"}, spec.GroupsRemove)
	assert.Equal(t, []string{"tier1/c"}, spec.AssigneeMappingRemove)
	// Assignment x overridden onto the file's map.
	assert.Equal(t, map[string]string{"x": "u2"}, spec.AssigneeMappingSet)
	// Label deltas augment the file's labels_add and populate labels_remove.
	assert.Equal(t, map[string][]string{"tier1/a": {"blocker", "smoke"}}, spec.LabelsAdd)
	assert.Equal(t, map[string][]string{"tier1/d": {"stale"}}, spec.LabelsRemove)
}

func TestOverlayUpdateFlags_NoFlagsLeavesSpecEmpty(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "update")

	var spec models.PlanUpdateSpec
	require.NoError(t, overlayUpdateFlags(cmd, &spec))
	assert.Nil(t, spec.Name)
	assert.Nil(t, spec.Completed)
	assert.Empty(t, spec.TestsAdd)
	assert.Empty(t, spec.AssigneeMappingSet)
}

// strPtrT is a string-pointer helper for table data in this test file.
func strPtrT(s string) *string { return &s }
