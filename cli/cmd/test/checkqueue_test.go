package test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseQueueItems_Scalar(t *testing.T) {
	got, err := parseQueueItems([]byte(`{"queueItem": 5}`))
	require.NoError(t, err)
	assert.Equal(t, []int{5}, got)
}

func TestParseQueueItems_Array(t *testing.T) {
	got, err := parseQueueItems([]byte(`{"queueItem": [5, 6, 7]}`))
	require.NoError(t, err)
	assert.Equal(t, []int{5, 6, 7}, got)
}

func TestParseQueueItems_MissingKey(t *testing.T) {
	// A payload without queueItem yields no items rather than an error.
	got, err := parseQueueItems([]byte(`{"other": 1}`))
	require.NoError(t, err)
	assert.Empty(t, got)
}

func TestParseQueueItems_Invalid(t *testing.T) {
	for _, bad := range []string{`not-json`, `{"queueItem": "five"}`, `{"queueItem": {}}`} {
		_, err := parseQueueItems([]byte(bad))
		require.Error(t, err, "input %q should be rejected", bad)
	}
}

// newCheckQueueCmd builds a command carrying just the check-queue flags so
// collectQueueItems can be unit-tested in isolation.
func newCheckQueueCmd() *cobra.Command {
	cmd := &cobra.Command{Use: "check-queue"}
	cmd.Flags().IntSlice("item", nil, "")
	cmd.Flags().String("file", "", "")
	return cmd
}

func TestCollectQueueItems_FlagsOnly(t *testing.T) {
	cmd := newCheckQueueCmd()
	require.NoError(t, cmd.Flags().Set("item", "3"))
	require.NoError(t, cmd.Flags().Set("item", "1"))

	got, err := collectQueueItems(cmd)
	require.NoError(t, err)
	// De-duplicated and sorted ascending.
	assert.Equal(t, []int{1, 3}, got)
}

func TestCollectQueueItems_MergeFileAndFlagsDedup(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "queued.json")
	require.NoError(t, os.WriteFile(path, []byte(`{"queueItem": [3, 9]}`), 0o600))

	cmd := newCheckQueueCmd()
	require.NoError(t, cmd.Flags().Set("item", "3"))
	require.NoError(t, cmd.Flags().Set("item", "5"))
	require.NoError(t, cmd.Flags().Set("file", path))

	got, err := collectQueueItems(cmd)
	require.NoError(t, err)
	// Union of {3,5} and {3,9}, de-duplicated and sorted.
	assert.Equal(t, []int{3, 5, 9}, got)
}

func TestCollectQueueItems_NoSource(t *testing.T) {
	_, err := collectQueueItems(newCheckQueueCmd())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "--item or --file")
}
