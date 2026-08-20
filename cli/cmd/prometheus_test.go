package cmd

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// writeBlock creates a minimal TSDB block directory (meta.json + chunks/000001)
// under parentDir/ulid, mimicking what Prometheus writes for a block.
func writeBlock(t *testing.T, parentDir, ulid string) {
	t.Helper()
	blockDir := filepath.Join(parentDir, ulid)
	require.NoError(t, os.MkdirAll(filepath.Join(blockDir, "chunks"), 0o755))
	require.NoError(t, os.WriteFile(filepath.Join(blockDir, "meta.json"), []byte(`{"version":1}`), 0o644))
	require.NoError(t, os.WriteFile(filepath.Join(blockDir, "chunks", "000001"), []byte("chunk-data"), 0o644))
}

// TestFlattenSnapshotDir_ReExtractExistingBlock reproduces ARGUS-195: a second
// `prometheus start` for the same run re-extracts the archive into a data dir
// that already holds the previously-flattened block. flattenSnapshotDir then
// tries to os.Rename the snapshot-wrapped block on top of the existing one at
// the data-dir root and fails, instead of treating the destination as already
// up to date.
func TestFlattenSnapshotDir_ReExtractExistingBlock(t *testing.T) {
	dataDir := t.TempDir()
	const ulid = "01KXX1KQAPXZBAGCXV0AJVZ75R"

	// Simulate a block left over from an earlier successful flatten.
	writeBlock(t, dataDir, ulid)

	// Simulate re-extracting the same snapshot archive into the same data
	// dir, producing the wrapper directory with the same block ULID again.
	wrapperDir := filepath.Join(dataDir, "20260719T111903Z-51a46eaea5666d12")
	writeBlock(t, wrapperDir, ulid)

	err := flattenSnapshotDir(dataDir)

	// Today's (buggy) behavior: the bare os.Rename onto an existing
	// destination directory fails, and flattenSnapshotDir surfaces that as
	// an error instead of reconciling the two copies of the block.
	require.Error(t, err, "expected flattenSnapshotDir to fail when the destination block already exists")
	assert.Contains(t, err.Error(), "moving")

	// The wrapper directory should still exist since the rename never
	// completed, leaving the run's data dir in the broken, non-flattened
	// state that triggers the failure on every subsequent start.
	_, statErr := os.Stat(wrapperDir)
	assert.NoError(t, statErr, "wrapper dir should remain when the move fails")
}
