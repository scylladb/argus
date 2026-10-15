package cache

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const testRunID = "22222222-2222-2222-2222-222222222222"

// putArchive writes a 1000-byte archive into the entry directory of key.
func putArchive(t *testing.T, c *Cache, key string) string {
	t.Helper()
	dir, err := c.EntryDir(key)
	require.NoError(t, err)
	archive := filepath.Join(dir, "monitor-set-22222222.tar.zst")
	require.NoError(t, os.WriteFile(archive, make([]byte, 1000), 0o644))
	return archive
}

func TestEntryDir_HoldsTheFilesSetWrites(t *testing.T) {
	c := New(t.TempDir())
	key := PrometheusLogKey(testRunID)
	require.NoError(t, Set(c, key, "monitor-set-22222222.tar.zst", "", time.Hour))

	dir, err := c.EntryDir(key)

	require.NoError(t, err)
	assert.FileExists(t, filepath.Join(dir, "meta.json"))
	assert.FileExists(t, filepath.Join(dir, "data.json"))
}

func TestEntryDir_RefusesDisabledCache(t *testing.T) {
	c := New(t.TempDir(), WithDisabled(true))

	_, err := c.EntryDir(PrometheusLogKey(testRunID))

	assert.ErrorIs(t, err, ErrDisabled)
}

func TestStats_CountsEveryFileInTheEntryDir(t *testing.T) {
	c := New(t.TempDir())
	key := PrometheusLogKey(testRunID)
	require.NoError(t, Set(c, key, "monitor-set-22222222.tar.zst", "", time.Hour))
	putArchive(t, c, key)
	dir, err := c.EntryDir(key)
	require.NoError(t, err)
	var want int64
	for _, name := range []string{"meta.json", "data.json", "monitor-set-22222222.tar.zst"} {
		info, err := os.Stat(filepath.Join(dir, name))
		require.NoError(t, err)
		want += info.Size()
	}

	stats, err := c.Stats()

	require.NoError(t, err)
	assert.Equal(t, want, stats.TotalBytes)
	assert.Equal(t, want, stats.Categories["prometheus-logs"].Bytes)
}

func TestPurgeExpired_RemovesFilesStoredInTheEntryDir(t *testing.T) {
	c := New(t.TempDir())
	key := PrometheusLogKey(testRunID)
	require.NoError(t, Set(c, key, "monitor-set-22222222.tar.zst", "", time.Nanosecond))
	archive := putArchive(t, c, key)

	assert.Equal(t, 1, c.PurgeExpired())

	assert.NoFileExists(t, archive)
}

func TestClear_RemovesFilesStoredInTheEntryDir(t *testing.T) {
	c := New(t.TempDir())
	key := PrometheusLogKey(testRunID)
	require.NoError(t, Set(c, key, "monitor-set-22222222.tar.zst", "", time.Hour))
	archive := putArchive(t, c, key)

	require.NoError(t, c.Clear())

	assert.NoFileExists(t, archive)
}

func TestKeysOutsideTheRootAreRefused(t *testing.T) {
	for _, key := range []string{"../x", "a/../../x", "/tmp/x", ".", "a/.."} {
		t.Run(key, func(t *testing.T) {
			base := t.TempDir()
			c := New(base)
			canary := filepath.Join(base, "x")
			require.NoError(t, os.WriteFile(canary, []byte("keep"), 0o644))

			_, _, getErr := Get[string](c, key)
			setErr := Set(c, key, "value", "", time.Hour)
			invalidateErr := c.Invalidate(key)

			assert.ErrorIs(t, getErr, ErrInvalidKey)
			assert.ErrorIs(t, setErr, ErrInvalidKey)
			assert.ErrorIs(t, invalidateErr, ErrInvalidKey)
			assert.FileExists(t, canary)
			entries, err := os.ReadDir(base)
			require.NoError(t, err)
			assert.Len(t, entries, 1, "nothing may be created next to the cache root")
		})
	}
}

// The cwd is process-wide, so this test must not run in parallel.
func TestEmptyRootTouchesNothing(t *testing.T) {
	t.Chdir(t.TempDir())
	require.NoError(t, os.MkdirAll(filepath.Join("cache", "x"), 0o755))
	require.NoError(t, os.WriteFile(filepath.Join("cache", "x", "meta.json"), []byte(`{}`), 0o644))
	c := New("")

	require.NoError(t, c.Clear())
	stats, err := c.Stats()
	require.NoError(t, err)
	c.PurgeExpired()
	require.NoError(t, Set(c, "x", "value", "", time.Hour))
	require.NoError(t, c.Invalidate("x"))

	assert.Zero(t, stats.Entries)
	assert.FileExists(t, filepath.Join("cache", "x", "meta.json"))
}

func TestClear_EmptiesADisabledCacheWithARoot(t *testing.T) {
	base := t.TempDir()
	require.NoError(t, Set(New(base), PrometheusLogKey(testRunID), "name", "", time.Hour))

	require.NoError(t, New(base, WithDisabled(true)).Clear())

	entries, err := os.ReadDir(filepath.Join(base, "cache"))
	require.NoError(t, err)
	assert.Empty(t, entries)
}
