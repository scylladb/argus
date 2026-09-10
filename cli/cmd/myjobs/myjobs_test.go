package myjobs

import (
	"testing"

	"github.com/scylladb/argus/cli/internal/services"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newParent registers the my-jobs tree on a throwaway parent, mirroring how
// cmd/myjobs.go wires it.
func newParent() *cobra.Command {
	parent := &cobra.Command{Use: "my-jobs"}
	Register(parent)
	return parent
}

func TestRegister_WiresAllSections(t *testing.T) {
	t.Parallel()
	parent := newParent()

	names := map[string]bool{}
	for _, c := range parent.Commands() {
		names[c.Name()] = true
	}
	for _, want := range []string{"todo", "done", "planned"} {
		assert.Truef(t, names[want], "expected %q sub-command", want)
	}
	assert.Len(t, parent.Commands(), 3)
}

func TestRegister_ParentListsRuns(t *testing.T) {
	t.Parallel()
	parent := newParent()
	assert.NotNil(t, parent.RunE, "bare my-jobs must list filtered runs")
	assert.Error(t, parent.Args(parent, []string{"extra"}))
}

func TestRegister_PersistentFlagsAreInherited(t *testing.T) {
	t.Parallel()
	parent := newParent()

	user := parent.PersistentFlags().Lookup("user")
	require.NotNil(t, user)
	assert.Equal(t, "u", user.Shorthand)
	require.NotNil(t, parent.PersistentFlags().Lookup("status"))
	assert.Equal(t, "s", parent.PersistentFlags().Lookup("status").Shorthand)
	require.NotNil(t, parent.PersistentFlags().Lookup("investigation-status"))
	assert.Equal(t, "i", parent.PersistentFlags().Lookup("investigation-status").Shorthand)

	// Persistent flags are shared across the tree, so each sub-command gets a
	// fresh parent to parse against.
	for _, name := range []string{"todo", "done", "planned"} {
		c := subCmd(t, newParent(), name)
		require.NoError(t, c.ParseFlags([]string{"--user", "alice", "--status", "failed,test_error", "-i", "in_progress"}))
		got, err := c.Flags().GetString("user")
		require.NoError(t, err)
		assert.Equalf(t, "alice", got, "%s should see the inherited --user flag", name)
		statuses, err := c.Flags().GetStringSlice("status")
		require.NoError(t, err)
		assert.Equal(t, []string{"failed", "test_error"}, statuses)
		inv, err := c.Flags().GetStringSlice("investigation-status")
		require.NoError(t, err)
		assert.Equal(t, []string{"in_progress"}, inv)
	}
}

// subCmd returns parent's sub-command called name.
func subCmd(t *testing.T, parent *cobra.Command, name string) *cobra.Command {
	t.Helper()
	for _, c := range parent.Commands() {
		if c.Name() == name {
			return c
		}
	}
	require.FailNowf(t, "sub-command not registered", "%q", name)
	return nil
}

func TestFilterFromFlags_DefaultsOnlyWhenRequested(t *testing.T) {
	t.Parallel()
	parent := newParent()

	withDefaults, err := filterFromFlags(parent, true)
	require.NoError(t, err)
	assert.Equal(t, services.DefaultRunFilter(), withDefaults)

	without, err := filterFromFlags(parent, false)
	require.NoError(t, err)
	assert.Equal(t, services.RunFilter{}, without)
}

func TestFilterFromFlags_ExplicitFlagReplacesItsDefaultOnly(t *testing.T) {
	t.Parallel()
	parent := newParent()
	require.NoError(t, parent.ParseFlags([]string{"--status", "Passed"}))

	filter, err := filterFromFlags(parent, true)
	require.NoError(t, err)
	assert.Equal(t, []string{"passed"}, filter.Statuses)
	assert.Equal(t, services.DefaultRunFilter().InvestigationStatuses, filter.InvestigationStatuses,
		"the untouched dimension keeps its default")
}

func TestFilterFromFlags_EmptyValueLiftsThatDefault(t *testing.T) {
	t.Parallel()
	parent := newParent()
	require.NoError(t, parent.ParseFlags([]string{"--status", ""}))

	filter, err := filterFromFlags(parent, true)
	require.NoError(t, err)
	assert.Empty(t, filter.Statuses, "an empty --status places no constraint on status")
	assert.Equal(t, services.DefaultRunFilter().InvestigationStatuses, filter.InvestigationStatuses)
	assert.True(t, filter.Matches("passed", "in_progress"))
	assert.False(t, filter.Matches("passed", "investigated"))
}

func TestFilterFromFlags_RejectsUnknownValues(t *testing.T) {
	t.Parallel()
	parent := newParent()
	require.NoError(t, parent.ParseFlags([]string{"--investigation-status", "done"}))

	_, err := filterFromFlags(parent, true)
	require.Error(t, err)
	assert.Contains(t, err.Error(), `unknown investigation status "done"`)
}

func TestSections_RejectPositionalArgs(t *testing.T) {
	t.Parallel()
	for _, c := range newParent().Commands() {
		assert.Errorf(t, c.Args(c, []string{"extra"}), "%s should reject positional args", c.Name())
	}
}
