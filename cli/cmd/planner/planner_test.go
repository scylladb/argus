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
	for _, want := range []string{"list", "get", "create", "delete"} {
		assert.Truef(t, names[want], "expected %q sub-command", want)
	}
}

func TestGet_TemplateFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	assert.NotNil(t, cmd.Flags().Lookup("template"))
}

func TestGet_RawFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	assert.NotNil(t, cmd.Flags().Lookup("raw"))
}

func TestGet_TemplateAndRawAreMutuallyExclusive(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "get")
	require.NoError(t, cmd.ParseFlags([]string{"--template", "--raw"}))
	err := cmd.ValidateFlagGroups()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "none of the others can be")
}

func TestList_RawFlagRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "list")
	assert.NotNil(t, cmd.Flags().Lookup("raw"))
}

func TestDelete_FlagsRegistered(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "delete")
	assert.NotNil(t, cmd.Flags().Lookup("delete-view"))
	assert.NotNil(t, cmd.Flags().Lookup("yes"))
	planID := cmd.Flags().Lookup("plan-id")
	require.NotNil(t, planID)
	assert.Equal(t, "p", planID.Shorthand)
}

func TestParseAssignments(t *testing.T) {
	t.Parallel()

	t.Run("merges over base and supports / in entity", func(t *testing.T) {
		t.Parallel()
		base := map[string]string{"tier1/a": "alice", "keep": "carol"}
		got, err := parseAssignments([]string{"tier1/a=bob", "tier2/b=dave"}, base)
		require.NoError(t, err)
		assert.Equal(t, map[string]string{
			"tier1/a": "bob",  // flag overrides base
			"tier2/b": "dave", // new entry
			"keep":    "carol",
		}, got)
		// Base is not mutated.
		assert.Equal(t, "alice", base["tier1/a"])
	})

	t.Run("rejects malformed values", func(t *testing.T) {
		t.Parallel()
		for _, bad := range []string{"noequals", "=bob", "entity=", "  =  "} {
			_, err := parseAssignments([]string{bad}, nil)
			require.Errorf(t, err, "expected error for %q", bad)
		}
	})
}

func TestOverlayFlags_FlagOverFilePrecedence(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "create")
	require.NoError(t, cmd.Flags().Set("name", "FlagName"))
	require.NoError(t, cmd.Flags().Set("test", "tier1/b"))
	require.NoError(t, cmd.Flags().Set("participant", "bob"))
	require.NoError(t, cmd.Flags().Set("assign", "x=u2"))
	require.NoError(t, cmd.Flags().Set("assign", "y=u3"))

	tmpl := models.PlanTemplate{
		Name:         "FileName",
		Release:      "scylla-2026.2",
		Tests:        []string{"tier1/a"},
		Participants: []string{"alice"},
		Assignments:  map[string]string{"x": "u1"},
	}

	require.NoError(t, overlayFlags(cmd, &tmpl))

	// Scalar flag overrides the file value.
	assert.Equal(t, "FlagName", tmpl.Name)
	// Release is untouched (flag not set).
	assert.Equal(t, "scylla-2026.2", tmpl.Release)
	// Collections augment the file collections.
	assert.Equal(t, []string{"tier1/a", "tier1/b"}, tmpl.Tests)
	assert.Equal(t, []string{"alice", "bob"}, tmpl.Participants)
	// Assignment x overridden, y added.
	assert.Equal(t, map[string]string{"x": "u2", "y": "u3"}, tmpl.Assignments)
}

func TestOverlayFlags_UnsetScalarsKeepFileValues(t *testing.T) {
	t.Parallel()
	cmd := newSubCmd(t, "create")

	tmpl := models.PlanTemplate{Name: "FileName", Owner: "alice"}
	require.NoError(t, overlayFlags(cmd, &tmpl))
	assert.Equal(t, "FileName", tmpl.Name)
	assert.Equal(t, "alice", tmpl.Owner)
}
