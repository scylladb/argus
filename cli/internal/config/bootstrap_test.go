//nolint:tparallel
package config_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/adrg/xdg"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// reloadXDG points the xdg package at dir for the duration of the test.
func reloadXDG(t *testing.T, dir string) {
	t.Helper()
	t.Setenv("XDG_CONFIG_HOME", dir)
	xdg.Reload()
	t.Cleanup(xdg.Reload)
}

// configPath returns the expected default config file path inside dir.
func configPath(dir string) string {
	return filepath.Join(dir, "argus-cli", "config.yaml")
}

// TestBootstrapCreatesFile verifies that on first run (no config file present)
// Load creates the file populated with built-in defaults.
func TestBootstrapCreatesFile(t *testing.T) {
	dir := t.TempDir()
	reloadXDG(t, dir)

	cfg, err := config.Load("", nil)
	require.NoError(t, err)
	assert.Equal(t, "https://argus.scylladb.com", cfg.URL)

	data, err := os.ReadFile(configPath(dir))
	require.NoError(t, err, "config file should have been created")
	assert.Contains(t, string(data), "argus.scylladb.com")
	t.Logf("written config:\n%s", data)
}

// TestBootstrapPersistsCustomURL verifies that when a cobra command has --url
// set to a custom value on first run, that value is written to the config file.
func TestBootstrapPersistsCustomURL(t *testing.T) {
	dir := t.TempDir()
	reloadXDG(t, dir)

	// Build a minimal cobra command tree that mirrors what root.go produces,
	// with --url already changed to the custom value (simulating the user
	// passing --url on the command line).
	cmd := newRootWithURL(t, "https://custom.example.com")

	cfg, err := config.Load("", cmd)
	require.NoError(t, err)
	assert.Equal(t, "https://custom.example.com", cfg.URL)

	data, err := os.ReadFile(configPath(dir))
	require.NoError(t, err, "config file should have been created")
	assert.Contains(t, string(data), "custom.example.com", "custom URL should be persisted")
	t.Logf("written config:\n%s", data)
}

// TestBootstrapDefaultURLWritten verifies that when --url is not changed by
// the user (flag still at its zero value / not set), the default URL ends up
// in the written config file via Viper's SetDefault.
func TestBootstrapDefaultURLWritten(t *testing.T) {
	dir := t.TempDir()
	reloadXDG(t, dir)

	cmd := newRootWithURL(t, "") // --url not provided, empty default on flag

	cfg, err := config.Load("", cmd)
	require.NoError(t, err)
	assert.Equal(t, "https://argus.scylladb.com", cfg.URL)

	data, err := os.ReadFile(configPath(dir))
	require.NoError(t, err, "config file should have been created")
	assert.Contains(t, string(data), "argus.scylladb.com")
}

// TestSecondRunReadsFile verifies that after bootstrap a second Load reads the
// persisted values from the file.
func TestSecondRunReadsFile(t *testing.T) {
	dir := t.TempDir()
	reloadXDG(t, dir)

	// First run — bootstraps the file.
	_, err := config.Load("", nil)
	require.NoError(t, err, "first Load should succeed")

	// Overwrite the file with a different URL.
	path := configPath(dir)
	require.NoError(t, os.WriteFile(path, []byte("url: https://from-file.example.com\n"), 0o600))

	// Second run — should read from the file, not use the default.
	cfg, err := config.Load("", nil)
	require.NoError(t, err, "second Load should succeed")
	assert.Equal(t, "https://from-file.example.com", cfg.URL)
}

// TestExplicitConfigFile verifies that cfgFile takes precedence over the XDG
// default location.
func TestExplicitConfigFile(t *testing.T) {
	dir := t.TempDir()
	reloadXDG(t, dir)

	explicit := filepath.Join(dir, "explicit.yaml")
	require.NoError(t, os.WriteFile(explicit, []byte("url: https://explicit.example.com\n"), 0o600))

	cfg, err := config.Load(explicit, nil)
	require.NoError(t, err)
	assert.Equal(t, "https://explicit.example.com", cfg.URL)
}

// newRootWithURL returns a *cobra.Command that mirrors the root command with a
// --url persistent flag set to urlValue (empty string = flag not changed by user).
func newRootWithURL(t *testing.T, urlValue string) *cobra.Command {
	t.Helper()
	root := &cobra.Command{Use: "argus"}
	root.PersistentFlags().String("url", "", "base URL of the Argus service")

	if urlValue != "" {
		require.NoError(t, root.PersistentFlags().Set("url", urlValue))
	}

	// Mark the flag as changed so Viper treats it as an explicit override,
	// matching real cobra behaviour when the user passes it on the CLI.
	if urlValue != "" {
		root.PersistentFlags().VisitAll(func(f *pflag.Flag) {
			if f.Name == "url" {
				f.Changed = true
			}
		})
	}

	return root
}
