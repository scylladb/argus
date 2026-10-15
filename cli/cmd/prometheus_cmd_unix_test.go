//go:build unix

package cmd

import (
	"archive/tar"
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/adrg/xdg"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// fakeDocker logs its arguments and keeps one container name in
// $FAKE_DOCKER_STATE. `run` fails when $FAKE_DOCKER_RUN_FAILS is set.
const fakeDocker = `#!/bin/sh
S="$FAKE_DOCKER_STATE"
echo "$@" >> "$S/log"
case "$1" in
  ps) [ -f "$S/name" ] && cat "$S/name"; exit 0;;
  run) [ -n "$FAKE_DOCKER_RUN_FAILS" ] && { echo "run failed" >&2; exit 125; }
       echo "$4" > "$S/name"; exit 0;;
  port) echo "0.0.0.0:12345"; exit 0;;
  rm) rm -f "$S/name"; exit 0;;
esac
exit 0
`

const promCmdArchive = "monitor-set-1e72eebe.tar.zst"

// promCmdEnv points the cache root at a temp dir, puts the fake docker on
// PATH, and stores the run's monitor-set archive in the cache. It returns the
// command context, the fake docker's state dir and the cache entry dir.
func promCmdEnv(t *testing.T) (context.Context, string, string) {
	t.Helper()
	t.Cleanup(xdg.Reload)
	cacheHome := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", cacheHome)
	xdg.Reload()
	require.True(t, strings.HasPrefix(config.CacheDir(), cacheHome), "the test must not touch the real cache")

	state := t.TempDir()
	bin := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(bin, "docker"), []byte(fakeDocker), 0o755))
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("FAKE_DOCKER_STATE", state)

	appCache := cache.New(config.CacheDir())
	key := cache.PrometheusLogKey(promTestRunID)
	require.NoError(t, cache.Set(appCache, key, promCmdArchive, "", time.Hour))
	entry, err := appCache.EntryDir(key)
	require.NoError(t, err)
	inner := tarZst(t, map[string]string{
		"20260426T074320Z-abc/01KXX1KQAPXZBAGCXV0AJVZ75R/meta.json": `{"version":1}`,
	})
	outer := tarZst(t, map[string]string{"monitor/prometheus_data_x.tar.zst": inner})
	require.NoError(t, os.WriteFile(filepath.Join(entry, promCmdArchive), []byte(outer), 0o644))

	// Nothing listens on port 1, so a test that reaches the API fails.
	client, err := api.New("http://127.0.0.1:1")
	require.NoError(t, err)
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	ctx = contextWithAPIClient(ctx, client)
	ctx = contextWithCache(ctx, appCache)
	return ctx, state, entry
}

func tarZst(t *testing.T, files map[string]string) string {
	t.Helper()
	var buf bytes.Buffer
	zw, err := zstd.NewWriter(&buf)
	require.NoError(t, err)
	tw := tar.NewWriter(zw)
	for name, data := range files {
		require.NoError(t, tw.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(data)), Typeflag: tar.TypeReg}))
		_, err := tw.Write([]byte(data))
		require.NoError(t, err)
	}
	require.NoError(t, tw.Close())
	require.NoError(t, zw.Close())
	return buf.String()
}

func runPromCmd(t *testing.T, ctx context.Context, run *cobra.Command, runID string) (string, error) {
	t.Helper()
	c := &cobra.Command{RunE: run.RunE}
	c.Flags().String("run-id", "", "")
	c.Flags().Bool("all", false, "")
	require.NoError(t, c.Flags().Set("run-id", runID))
	c.SetContext(ctx)
	var out bytes.Buffer
	c.SetOut(&out)
	c.SetErr(&out)
	err := c.RunE(c, nil)
	return out.String(), err
}

func dockerLog(t *testing.T, state string) string {
	t.Helper()
	log, err := os.ReadFile(filepath.Join(state, "log"))
	require.NoError(t, err)
	return string(log)
}

func TestPromStart_ReusesTheCachedArchive(t *testing.T) {
	ctx, state, entry := promCmdEnv(t)

	out, err := runPromCmd(t, ctx, promStartCmd, promTestRunID)

	require.NoError(t, err)
	assert.Equal(t, "Prometheus running at http://localhost:12345\n", out)
	assert.FileExists(t, filepath.Join(entry, promCmdArchive))
	runDir := filepath.Join(promDataRoot(), promTestRunID)
	assert.FileExists(t, filepath.Join(runDir, "run_id"))
	assert.DirExists(t, filepath.Join(runDir, "01KXX1KQAPXZBAGCXV0AJVZ75R"))
	assert.Contains(t, dockerLog(t, state), "--user ")
}

func TestPromStart_FailedRunLeavesNoRunDir(t *testing.T) {
	ctx, _, entry := promCmdEnv(t)
	t.Setenv("FAKE_DOCKER_RUN_FAILS", "1")

	_, err := runPromCmd(t, ctx, promStartCmd, promTestRunID)

	require.ErrorContains(t, err, "docker run failed")
	assert.NoDirExists(t, filepath.Join(promDataRoot(), promTestRunID))
	assert.FileExists(t, filepath.Join(entry, promCmdArchive))
}

// Another start of the run holds the directory and has no container yet. A
// second start must not touch it, nor remove it when it fails.
func TestPromStart_RefusesARunDirThatAlreadyExists(t *testing.T) {
	ctx, state, _ := promCmdEnv(t)
	runDir := filepath.Join(promDataRoot(), promTestRunID)
	require.NoError(t, os.MkdirAll(runDir, 0o755))
	marker := filepath.Join(runDir, "prometheus.yml")
	require.NoError(t, os.WriteFile(marker, []byte("in progress"), 0o644))

	_, err := runPromCmd(t, ctx, promStartCmd, promTestRunID)

	require.ErrorContains(t, err, "already exists")
	assert.FileExists(t, marker)
	assert.NotContains(t, dockerLog(t, state), "run ")
}

func TestPromStop_RemovesTheRunDirAndKeepsTheArchive(t *testing.T) {
	ctx, _, entry := promCmdEnv(t)
	_, err := runPromCmd(t, ctx, promStartCmd, promTestRunID)
	require.NoError(t, err)

	out, err := runPromCmd(t, ctx, promStopCmd, promTestRunID)

	require.NoError(t, err)
	assert.Equal(t, "Stopped and removed argus-prom-1e72eebe\n", out)
	assert.NoDirExists(t, filepath.Join(promDataRoot(), promTestRunID))
	assert.FileExists(t, filepath.Join(entry, promCmdArchive))
}
