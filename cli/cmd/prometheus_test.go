package cmd

import (
	"bytes"
	"errors"
	"io"
	"os"
	"path/filepath"
	"slices"
	"testing"
	"time"

	"github.com/scylladb/argus/cli/internal/cache"
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

	// flattenSnapshotDir must be idempotent: re-extracting the same block
	// into an already-flattened data dir should succeed by treating the
	// existing destination as already up to date, not error out.
	require.NoError(t, err, "flattenSnapshotDir should tolerate a block that was already extracted")

	// The block must end up in place at the data-dir root.
	metaPath := filepath.Join(dataDir, ulid, "meta.json")
	assert.FileExists(t, metaPath, "block should be present at the data-dir root")
	chunkPath := filepath.Join(dataDir, ulid, "chunks", "000001")
	assert.FileExists(t, chunkPath, "block chunk data should be present at the data-dir root")

	// The wrapper directory should be cleaned up after a successful flatten.
	_, statErr := os.Stat(wrapperDir)
	assert.True(t, os.IsNotExist(statErr), "wrapper dir should be removed after a successful flatten")
}

func TestPromRunDir_ReturnsDirUnderRoot(t *testing.T) {
	root := t.TempDir()
	const runID = "1e72eebe-a48d-4a3e-a560-c6ad0d85b1af"

	dir, err := promRunDir(root, runID)

	require.NoError(t, err)
	assert.Equal(t, filepath.Join(root, runID), dir)
}

func TestPromRunDir_RejectsRunIDOutsideRoot(t *testing.T) {
	root := t.TempDir()
	for _, runID := range []string{"", ".", "..", "../escape", "../../..", "nested/dir", "x/../y"} {
		_, err := promRunDir(root, runID)
		assert.ErrorContains(t, err, "invalid run ID", "run ID %q", runID)
	}
}

func TestChildPath_RejectsServerNameWithPath(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"../x-monitor-set.tar.zst", "sub/monitor-set.tar.zst"} {
		_, err := childPath(root, name)
		assert.Error(t, err, "name %q", name)
	}
}

func TestPromDockerRunArgs_RunsAsCallingUserBeforeImage(t *testing.T) {
	args := promDockerRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001)

	user := slices.Index(args, "--user")
	require.NotEqual(t, -1, user, "args=%v", args)
	assert.Equal(t, "1000:1001", args[user+1])
	assert.Less(t, user, slices.Index(args, promImage), "--user must precede the image")
}

func TestPromDockerRunArgs_OmitsUserWhenUIDUnknown(t *testing.T) {
	args := promDockerRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", -1, -1)

	assert.NotContains(t, args, "--user")
}

func TestWritePromConfig_WritesTheScrapeConfig(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "prometheus.yml")

	require.NoError(t, writePromConfig(configPath, promConfig))

	got, err := os.ReadFile(configPath)
	require.NoError(t, err)
	assert.Contains(t, string(got), "scrape_interval: 15s")
	assert.Contains(t, string(got), "evaluation_interval: 15s")
}

func TestWritePromConfig_ReportsAFailedWrite(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "absent", "prometheus.yml")

	err := writePromConfig(configPath, promConfig)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "writing prometheus config")
}

const promTestRunID = "1e72eebe-a48d-4a3e-a560-c6ad0d85b1af"

// listed returns a container lister for removeOrphanDataDirs.
func listed(names ...string) func() ([]string, error) {
	return func() ([]string, error) { return names, nil }
}

// makeRunDir creates root/runID, with a run_id file when started is true.
func makeRunDir(t *testing.T, root, runID string, started bool) string {
	t.Helper()
	dir := filepath.Join(root, runID)
	require.NoError(t, os.MkdirAll(filepath.Join(dir, "wal"), 0o755))
	if started {
		require.NoError(t, os.WriteFile(filepath.Join(dir, "run_id"), []byte(runID), 0o644))
	}
	return dir
}

func TestRemoveOrphanDataDirs_RemovesDirOfRemovedContainer(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, true)
	var warnings bytes.Buffer

	removeOrphanDataDirs(&warnings, root, listed())

	assert.NoDirExists(t, dir)
	assert.Empty(t, warnings.String())
}

func TestRemoveOrphanDataDirs_KeepsDirWithContainer(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, true)

	removeOrphanDataDirs(io.Discard, root, listed(promContainerName(promTestRunID)))

	assert.DirExists(t, dir)
}

func TestRemoveOrphanDataDirs_KeepsRecentDirOfStartInProgress(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, false)

	removeOrphanDataDirs(io.Discard, root, listed())

	assert.DirExists(t, dir)
}

// The containers are listed after the scan: a run whose container starts
// during the sweep wrote no run_id yet when the scan saw its directory.
func TestRemoveOrphanDataDirs_KeepsDirWhoseContainerStartsDuringTheSweep(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, false)
	startsNow := func() ([]string, error) {
		require.NoError(t, os.WriteFile(filepath.Join(dir, "run_id"), []byte(promTestRunID), 0o644))
		return nil, nil
	}

	removeOrphanDataDirs(io.Discard, root, startsNow)

	assert.DirExists(t, dir)
}

func TestRemoveOrphanDataDirs_WarnsWhenContainersCannotBeListed(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, true)
	var warnings bytes.Buffer

	removeOrphanDataDirs(&warnings, root, func() ([]string, error) { return nil, errors.New("docker ps: exit status 1") })

	assert.DirExists(t, dir)
	assert.Contains(t, warnings.String(), "warning: skipping prometheus data cleanup")
}

func TestRemoveOrphanDataDirs_RemovesStaleDirOfAbortedStart(t *testing.T) {
	root := t.TempDir()
	dir := makeRunDir(t, root, promTestRunID, false)
	old := time.Now().Add(-2 * promMaxTTL)
	require.NoError(t, os.Chtimes(dir, old, old))

	removeOrphanDataDirs(io.Discard, root, listed())

	assert.NoDirExists(t, dir)
}

func TestRemoveOrphanDataDirs_IgnoresMissingRoot(t *testing.T) {
	var warnings bytes.Buffer

	removeOrphanDataDirs(&warnings, filepath.Join(t.TempDir(), "absent"), listed())

	assert.Empty(t, warnings.String())
}

func TestCacheArchive_PutsArchiveInCacheEntry(t *testing.T) {
	c := cache.New(t.TempDir())
	key := cache.PrometheusLogKey(promTestRunID)
	archive := filepath.Join(t.TempDir(), "monitor-set-1e72eebe.tar.zst")
	require.NoError(t, os.WriteFile(archive, []byte("archive"), 0o644))

	require.NoError(t, cacheArchive(c, key, archive))

	assert.NoFileExists(t, archive)
	cached := cachedArchivePath(c, key)
	require.NotEmpty(t, cached)
	got, err := os.ReadFile(cached)
	require.NoError(t, err)
	assert.Equal(t, "archive", string(got))
}

func TestCacheArchive_DropsArchiveWhenCacheDisabled(t *testing.T) {
	c := cache.New(t.TempDir(), cache.WithDisabled(true))
	key := cache.PrometheusLogKey(promTestRunID)
	archive := filepath.Join(t.TempDir(), "monitor-set-1e72eebe.tar.zst")
	require.NoError(t, os.WriteFile(archive, []byte("archive"), 0o644))

	require.NoError(t, cacheArchive(c, key, archive))

	assert.NoFileExists(t, archive)
	assert.Empty(t, cachedArchivePath(c, key))
}

func TestClaimRunDir_CreatesTheDir(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "prometheus", promTestRunID)

	require.NoError(t, claimRunDir(dir))

	assert.DirExists(t, dir)
}

// The dir of a start in progress, or a leftover the sweep could not remove.
func TestClaimRunDir_RefusesAnExistingDir(t *testing.T) {
	dir := makeRunDir(t, t.TempDir(), promTestRunID, false)
	marker := filepath.Join(dir, "wal", "00000000")
	require.NoError(t, os.WriteFile(marker, []byte("wal"), 0o644))

	err := claimRunDir(dir)

	require.Error(t, err)
	assert.Contains(t, err.Error(), dir)
	assert.Contains(t, err.Error(), "already exists")
	assert.FileExists(t, marker)
}

func TestCachedArchivePath_MissesWhenEntryHasNoArchive(t *testing.T) {
	c := cache.New(t.TempDir())
	key := cache.PrometheusLogKey(promTestRunID)
	require.NoError(t, cache.Set(c, key, "monitor-set-1e72eebe.tar.zst", "", time.Hour))

	assert.Empty(t, cachedArchivePath(c, key))
}

func TestCachedArchivePath_MissesOnTamperedName(t *testing.T) {
	c := cache.New(t.TempDir())
	key := cache.PrometheusLogKey(promTestRunID)
	require.NoError(t, cache.Set(c, key, "../../x", "", time.Hour))

	assert.Empty(t, cachedArchivePath(c, key))
}
