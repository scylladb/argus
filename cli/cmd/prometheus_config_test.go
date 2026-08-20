//go:build unix

package cmd

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// The umask is process wide, so none of the tests below may call t.Parallel,
// and none of the parallel tests in this package may touch the filesystem.
func withUmask(t *testing.T, mask int) {
	t.Helper()
	previous := syscall.Umask(mask)
	t.Cleanup(func() { syscall.Umask(previous) })
}

func TestWritePromConfig_KeepsModeUnderAnyUmask(t *testing.T) {
	for _, mask := range []int{0o000, 0o022, 0o027, 0o077, 0o777} {
		t.Run("", func(t *testing.T) {
			// The temp directory is made before the umask changes: at 0777 it
			// would otherwise land as 0000 and nothing could be written in it.
			configPath := filepath.Join(t.TempDir(), "prometheus.yml")
			withUmask(t, mask)

			require.NoError(t, writePromConfig(configPath, promConfig))

			info, err := os.Stat(configPath)
			require.NoError(t, err)
			assert.Equal(t, os.FileMode(0o644), info.Mode().Perm(),
				"umask %04o must not reach the config the container reads", mask)
		})
	}
}

// The container runs as uid 65534 and reads the config through a bind mount, so
// the other-read bit is the one that decides whether prometheus starts.
func TestWritePromConfig_StaysReadableByTheContainerUser(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "prometheus.yml")
	withUmask(t, 0o027)

	require.NoError(t, writePromConfig(configPath, promConfig))

	info, err := os.Stat(configPath)
	require.NoError(t, err)
	assert.NotZero(t, info.Mode().Perm()&0o004, "config is not world readable")
}

// Pins the premise the fix rests on. Without the Chmod the write below is all
// writePromConfig does, and this test says what that alone produces.
func TestWritePromConfig_UmaskWouldOtherwiseStripTheMode(t *testing.T) {
	dir := t.TempDir()
	withUmask(t, 0o027)
	bare := filepath.Join(dir, "bare.yml")

	require.NoError(t, os.WriteFile(bare, []byte(promConfig), 0o644))

	info, err := os.Stat(bare)
	require.NoError(t, err)
	require.Equal(t, os.FileMode(0o640), info.Mode().Perm(),
		"a plain WriteFile is expected to lose the other-read bit here")

	fixed := filepath.Join(dir, "prometheus.yml")
	require.NoError(t, writePromConfig(fixed, promConfig))

	info, err = os.Stat(fixed)
	require.NoError(t, err)
	assert.Equal(t, os.FileMode(0o644), info.Mode().Perm())
}

// A second `prometheus start` for the same run reuses the cached data
// directory, so the file it writes over may already carry a stricter mode.
func TestWritePromConfig_RepairsAnExistingStrictMode(t *testing.T) {
	configPath := filepath.Join(t.TempDir(), "prometheus.yml")
	withUmask(t, 0o027)
	require.NoError(t, os.WriteFile(configPath, []byte("stale"), 0o600))
	require.NoError(t, os.Chmod(configPath, 0o600))

	require.NoError(t, writePromConfig(configPath, promConfig))

	info, err := os.Stat(configPath)
	require.NoError(t, err)
	assert.Equal(t, os.FileMode(0o644), info.Mode().Perm())

	got, err := os.ReadFile(configPath)
	require.NoError(t, err)
	assert.Equal(t, promConfig, string(got))
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

// The data directory is the other half of the same guarantee: the container
// writes its TSDB blocks there as uid 65534.
func TestChmodRecursive_KeepsModeUnderAnyUmask(t *testing.T) {
	dataDir := t.TempDir()
	withUmask(t, 0o077)
	nested := filepath.Join(dataDir, "wal")
	require.NoError(t, os.Mkdir(nested, 0o755))
	block := filepath.Join(nested, "00000001")
	require.NoError(t, os.WriteFile(block, []byte("block"), 0o644))

	require.NoError(t, chmodRecursive(dataDir, 0o777))

	for _, path := range []string{dataDir, nested, block} {
		info, err := os.Stat(path)
		require.NoError(t, err)
		assert.Equal(t, os.FileMode(0o777), info.Mode().Perm(), "path=%s", path)
	}
}
