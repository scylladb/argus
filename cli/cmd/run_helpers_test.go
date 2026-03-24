package cmd_test

import (
	"testing"

	"github.com/scylladb/argus/cli/cmd"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// parseTimeFlag
// --------------------------------------------------------------------------

func TestParseTimeFlag_Empty(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseTimeFlag("")
	require.NoError(t, err)
	assert.Equal(t, int64(0), ts)
}

func TestParseTimeFlag_UnixTimestamp(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseTimeFlag("1742428800")
	require.NoError(t, err)
	assert.Equal(t, int64(1742428800), ts)
}

func TestParseTimeFlag_RFC3339(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseTimeFlag("2026-03-20T00:00:00Z")
	require.NoError(t, err)
	assert.Equal(t, int64(1773964800), ts)
}

func TestParseTimeFlag_RFC3339WithOffset(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseTimeFlag("2026-03-20T02:00:00+02:00")
	require.NoError(t, err)
	assert.Equal(t, int64(1773964800), ts)
}

func TestParseTimeFlag_Invalid(t *testing.T) {
	t.Parallel()
	_, err := cmd.ParseTimeFlag("not-a-time")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid time")
}

// --------------------------------------------------------------------------
// parseEventTimestamp
// --------------------------------------------------------------------------

func TestParseEventTimestamp_Empty(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseEventTimestamp("")
	require.NoError(t, err)
	assert.Equal(t, int64(0), ts)
}

func TestParseEventTimestamp_ISO(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseEventTimestamp("2026-03-23T01:19:14Z")
	require.NoError(t, err)
	assert.Greater(t, ts, int64(0))
}

func TestParseEventTimestamp_ISOMillis(t *testing.T) {
	t.Parallel()
	ts, err := cmd.ParseEventTimestamp("2026-03-23T01:19:14.818Z")
	require.NoError(t, err)
	assert.Greater(t, ts, int64(0))
}

func TestParseEventTimestamp_Invalid(t *testing.T) {
	t.Parallel()
	_, err := cmd.ParseEventTimestamp("garbage")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "cannot parse")
}

// --------------------------------------------------------------------------
// parseRunID / isValidUUID
// --------------------------------------------------------------------------

func TestParseRunID_Valid(t *testing.T) {
	t.Parallel()
	id, err := cmd.ParseRunID("9f3ab443-a701-49b3-ab9d-06a1b7546ef8")
	require.NoError(t, err)
	assert.Equal(t, "9f3ab443-a701-49b3-ab9d-06a1b7546ef8", id)
}

func TestParseRunID_Invalid(t *testing.T) {
	t.Parallel()
	_, err := cmd.ParseRunID("not-a-uuid")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid run_id")
}

func TestIsValidUUID(t *testing.T) {
	t.Parallel()
	assert.True(t, cmd.IsValidUUID("9f3ab443-a701-49b3-ab9d-06a1b7546ef8"))
	assert.False(t, cmd.IsValidUUID("too-short"))
	assert.False(t, cmd.IsValidUUID("9f3ab443Xa701-49b3-ab9d-06a1b7546ef8")) // bad separator
	assert.False(t, cmd.IsValidUUID("zf3ab443-a701-49b3-ab9d-06a1b7546ef8")) // bad hex
}

// --------------------------------------------------------------------------
// formatTimestamp
// --------------------------------------------------------------------------

func TestFormatTimestamp_Int64(t *testing.T) {
	t.Parallel()
	assert.Equal(t, "2025-03-20 00:00:00 UTC", cmd.FormatTimestamp(int64(1742428800)))
}

func TestFormatTimestamp_Float64(t *testing.T) {
	t.Parallel()
	assert.Equal(t, "2025-03-20 00:00:00 UTC", cmd.FormatTimestamp(float64(1742428800)))
}

func TestFormatTimestamp_ISOString(t *testing.T) {
	t.Parallel()
	result := cmd.FormatTimestamp("2026-03-23T01:19:14Z")
	assert.Equal(t, "2026-03-23 01:19:14 UTC", result)
}

func TestFormatTimestamp_Zero(t *testing.T) {
	t.Parallel()
	assert.Equal(t, "", cmd.FormatTimestamp(int64(0)))
	assert.Equal(t, "", cmd.FormatTimestamp(float64(0)))
	assert.Equal(t, "", cmd.FormatTimestamp(""))
	assert.Equal(t, "", cmd.FormatTimestamp(nil))
}
