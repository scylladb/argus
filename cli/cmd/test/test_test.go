package test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseParams(t *testing.T) {
	got, err := parseParams([]string{"backend=aws", "region=eu-west-1"})
	require.NoError(t, err)
	assert.Equal(t, map[string]any{"backend": "aws", "region": "eu-west-1"}, got)
}

func TestParseParams_EmptyValueAndEquals(t *testing.T) {
	// Empty value is allowed; the first "=" splits, so values may contain "=".
	got, err := parseParams([]string{"empty=", "expr=a=b"})
	require.NoError(t, err)
	assert.Equal(t, map[string]any{"empty": "", "expr": "a=b"}, got)
}

func TestParseParams_Invalid(t *testing.T) {
	for _, bad := range []string{"noequals", "=value", "  =x"} {
		_, err := parseParams([]string{bad})
		require.Error(t, err, "input %q should be rejected", bad)
	}
}

func TestParseParams_Nil(t *testing.T) {
	got, err := parseParams(nil)
	require.NoError(t, err)
	assert.Nil(t, got)
}

// newExecuteCmd builds a minimal command carrying just the flags loadParamsFile
// and buildNumberFlag read, so the helpers can be unit-tested in isolation.
func newExecuteCmd() *cobra.Command {
	cmd := &cobra.Command{Use: "execute"}
	cmd.Flags().String("file", "", "")
	cmd.Flags().Int("build-number", 0, "")
	return cmd
}

func TestLoadParamsFile_Unset(t *testing.T) {
	got, err := loadParamsFile(newExecuteCmd())
	require.NoError(t, err)
	assert.Nil(t, got)
}

func TestLoadParamsFile_ReadsMap(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "params.json")
	require.NoError(t, os.WriteFile(path, []byte(`{"backend":"aws","test_duration":"600"}`), 0o600))

	cmd := newExecuteCmd()
	require.NoError(t, cmd.Flags().Set("file", path))

	got, err := loadParamsFile(cmd)
	require.NoError(t, err)
	assert.Equal(t, map[string]any{"backend": "aws", "test_duration": "600"}, got)
}

func TestLoadParamsFile_InvalidJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.json")
	require.NoError(t, os.WriteFile(path, []byte(`not-json`), 0o600))

	cmd := newExecuteCmd()
	require.NoError(t, cmd.Flags().Set("file", path))

	_, err := loadParamsFile(cmd)
	require.Error(t, err)
}

func TestBuildNumberFlag(t *testing.T) {
	// Unset → nil (backend seeds from last build).
	assert.Nil(t, buildNumberFlag(newExecuteCmd()))

	cmd := newExecuteCmd()
	require.NoError(t, cmd.Flags().Set("build-number", "42"))
	n := buildNumberFlag(cmd)
	require.NotNil(t, n)
	assert.Equal(t, 42, *n)
}
