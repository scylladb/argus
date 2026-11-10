package cmd

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"sync/atomic"
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

func TestPromRunArgs_RunsAsCallingUserBeforeImage(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, false)

	user := slices.Index(args, "--user")
	require.NotEqual(t, -1, user, "args=%v", args)
	assert.Equal(t, "1000:1001", args[user+1])
	assert.Less(t, user, slices.Index(args, promImage), "--user must precede the image")
}

func TestPromRunArgs_OmitsUserWhenUIDUnknown(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", -1, -1, true)

	assert.NotContains(t, args, "--user")
	assert.NotContains(t, args, "--userns=keep-id")
}

func TestPromRunArgs_RelabelsMountsForSELinux(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, false)

	assert.Contains(t, args, "/data:/prometheus:z")
	assert.Contains(t, args, "/data/prometheus.yml:/etc/prometheus/prometheus.yml:ro,z")
}

// Podman resolves no short image name without a TTY.
func TestPromRunArgs_NamesTheImageRegistry(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, false)

	assert.Contains(t, args, "docker.io/prom/prometheus:latest")
}

func TestPromRunArgs_PublishesARandomPortOnLoopbackOnly(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, false)

	publish := slices.Index(args, "-p")
	require.NotEqual(t, -1, publish, "args=%v", args)
	assert.Equal(t, "127.0.0.1::9090", args[publish+1])
}

func TestPromRunArgs_KeepsTheUserIDsOnRootlessPodman(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, true)

	keepID := slices.Index(args, "--userns=keep-id")
	require.NotEqual(t, -1, keepID, "args=%v", args)
	assert.Less(t, keepID, slices.Index(args, promImage), "--userns must precede the image")
	assert.Contains(t, args, "1000:1001")
}

func TestPromRunArgs_OmitsKeepIDWhenNotAsked(t *testing.T) {
	args := promRunArgs("argus-prom-1e72eebe", "/data", "/data/prometheus.yml", 1000, 1001, false)

	assert.NotContains(t, args, "--userns=keep-id")
}

func TestStaleContainers_ParsesDockerCreatedAt(t *testing.T) {
	out := "argus-prom-old\t2026-11-10 10:05:47 +0100 CET\n" +
		"argus-prom-new\t2026-11-10 11:05:47 +0100 CET\n"

	stale := staleContainers(out, time.Date(2026, 11, 10, 9, 30, 0, 0, time.UTC))

	assert.Equal(t, []string{"argus-prom-old"}, stale)
}

func TestStaleContainers_ParsesPodmanCreatedAt(t *testing.T) {
	out := "argus-prom-old\t2026-11-10 09:05:42.615310779 +0000 UTC\n" +
		"argus-prom-new\t2026-11-10 09:35:42.615310779 +0000 UTC\n"

	stale := staleContainers(out, time.Date(2026, 11, 10, 9, 30, 0, 0, time.UTC))

	assert.Equal(t, []string{"argus-prom-old"}, stale)
}

func TestStaleContainers_SkipsLinesItCannotParse(t *testing.T) {
	out := "argus-prom-a\tLess than a second ago\nargus-prom-b\n\n"

	assert.Empty(t, staleContainers(out, time.Now()))
}

func lookPathOf(found ...string) func(string) (string, error) {
	return func(name string) (string, error) {
		if slices.Contains(found, name) {
			return "/usr/bin/" + name, nil
		}
		return "", fmt.Errorf("exec: %q: executable file not found in $PATH", name)
	}
}

func noEnv(string) string { return "" }

func TestResolveEngine_PrefersDocker(t *testing.T) {
	engine, err := resolveEngine(noEnv, lookPathOf("docker", "podman"))

	require.NoError(t, err)
	assert.Equal(t, "docker", engine)
}

func TestResolveEngine_FallsBackToPodman(t *testing.T) {
	engine, err := resolveEngine(noEnv, lookPathOf("podman"))

	require.NoError(t, err)
	assert.Equal(t, "podman", engine)
}

func TestResolveEngine_TakesTheEngineFromTheEnv(t *testing.T) {
	getenv := func(name string) string { return map[string]string{promEngineEnv: "podman"}[name] }

	engine, err := resolveEngine(getenv, lookPathOf("docker", "podman"))

	require.NoError(t, err)
	assert.Equal(t, "podman", engine)
}

func TestResolveEngine_ReportsAMissingEngineFromTheEnv(t *testing.T) {
	getenv := func(name string) string { return map[string]string{promEngineEnv: "nerdctl"}[name] }

	_, err := resolveEngine(getenv, lookPathOf("docker"))

	require.ErrorContains(t, err, promEngineEnv+"=nerdctl")
	assert.ErrorContains(t, err, "executable file not found")
}

func TestResolveEngine_NamesBothEnginesAndTheEnvWhenNoneIsFound(t *testing.T) {
	_, err := resolveEngine(noEnv, lookPathOf())

	require.Error(t, err)
	for _, s := range []string{"docker", "podman", promEngineEnv} {
		assert.Contains(t, err.Error(), s)
	}
}

func TestWaitPromReady_ReturnsOnceReady(t *testing.T) {
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/-/ready", r.URL.Path)
		if calls.Add(1) < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
	}))
	defer srv.Close()

	require.NoError(t, waitPromReady(t.Context(), srv.URL, func() error { return nil }, 10*time.Second))
	assert.Equal(t, int32(3), calls.Load())
}

func TestWaitPromReady_FailsWhenContainerStops(t *testing.T) {
	stopped := errors.New("container exited")

	err := waitPromReady(t.Context(), "http://127.0.0.1:1", func() error { return stopped }, 10*time.Second)

	assert.ErrorIs(t, err, stopped)
}

func TestWaitPromReady_ReportsCancelNotTimeout(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	cancel()

	err := waitPromReady(ctx, "http://127.0.0.1:1", func() error { return nil }, 10*time.Second)

	assert.ErrorIs(t, err, context.Canceled)
}

func TestWaitPromReady_FailsAfterTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	err := waitPromReady(t.Context(), srv.URL, func() error { return nil }, time.Second)

	assert.ErrorContains(t, err, "not ready after 1s")
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
