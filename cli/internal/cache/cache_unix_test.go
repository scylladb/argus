//go:build unix

package cache

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// The purge runs in the background and dies with the process, so a removal
// can stop halfway. A file it cannot remove stands in for that cut: the entry
// must keep its meta.json, so the next purge still finds it.
func TestPurgeExpired_KeepsMetaUntilTheEntryIsEmpty(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root removes files regardless of their mode")
	}
	c := New(t.TempDir())
	key := PrometheusLogKey(testRunID)
	require.NoError(t, Set(c, key, "monitor-set-22222222.tar.zst", "", time.Nanosecond))
	dir, err := c.EntryDir(key)
	require.NoError(t, err)
	stuck := filepath.Join(dir, "stuck")
	require.NoError(t, os.MkdirAll(stuck, 0o755))
	require.NoError(t, os.WriteFile(filepath.Join(stuck, "file"), []byte("x"), 0o644))
	require.NoError(t, os.Chmod(stuck, 0o500))
	t.Cleanup(func() { _ = os.Chmod(stuck, 0o755) })

	assert.Zero(t, c.PurgeExpired())

	assert.FileExists(t, filepath.Join(dir, "meta.json"))
	require.NoError(t, os.Chmod(stuck, 0o755))
	assert.Equal(t, 1, c.PurgeExpired(), "the next purge finishes the entry")
	assert.NoDirExists(t, dir)
}
