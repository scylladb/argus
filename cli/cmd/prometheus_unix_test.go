//go:build unix

package cmd

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// A wal/ the user cannot write stands in for one that an earlier CLI version
// left behind as nobody.
func TestRemovePromData_WarnsWhenFilesCannotBeRemoved(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root removes files regardless of their mode")
	}
	dir := filepath.Join(t.TempDir(), promTestRunID)
	wal := filepath.Join(dir, "wal")
	require.NoError(t, os.MkdirAll(wal, 0o755))
	require.NoError(t, os.WriteFile(filepath.Join(wal, "00000000"), []byte("wal"), 0o644))
	require.NoError(t, os.Chmod(wal, 0o500))
	t.Cleanup(func() { _ = os.Chmod(wal, 0o755) })
	var warnings bytes.Buffer

	removePromData(&warnings, dir)

	assert.Contains(t, warnings.String(), "warning")
	assert.Contains(t, warnings.String(), filepath.Join(wal, "00000000"))
	assert.DirExists(t, dir)
}
