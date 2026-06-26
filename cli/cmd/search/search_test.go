package search_test

import (
	"testing"

	"github.com/scylladb/argus/cli/cmd/search"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// findSearchCmd registers the search command on a throwaway parent and returns
// it, mirroring how cmd/search.go wires it onto rootCmd.
func findSearchCmd(t *testing.T) *cobra.Command {
	t.Helper()
	parent := &cobra.Command{Use: "argus"}
	search.Register(parent)
	for _, c := range parent.Commands() {
		if c.Name() == "search" {
			return c
		}
	}
	require.FailNow(t, "search command was not registered")
	return nil
}

func TestRegister_WiresSearchCommand(t *testing.T) {
	t.Parallel()
	cmd := findSearchCmd(t)

	// The release scoping flag is present with its short form.
	flag := cmd.Flags().Lookup("release")
	require.NotNil(t, flag)
	assert.Equal(t, "r", flag.Shorthand)
}

func TestSearch_RequiresQueryArg(t *testing.T) {
	t.Parallel()
	cmd := findSearchCmd(t)

	// Args validator rejects an empty query and accepts one or more terms.
	require.Error(t, cmd.Args(cmd, []string{}))
	require.NoError(t, cmd.Args(cmd, []string{"longevity"}))
	require.NoError(t, cmd.Args(cmd, []string{"type:group", "release:2026.2"}))
}
