package keychain_test

import (
	"testing"

	gokeyring "github.com/zalando/go-keyring"

	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setupMock(t *testing.T) {
	t.Helper()
	gokeyring.MockInit()
}

func TestStore_And_Load(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.Store("tok-abc"))

	got, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, "tok-abc", got)
}

func TestLoad_NotFound(t *testing.T) {
	setupMock(t)

	_, err := keychain.Load()
	require.Error(t, err)
	assert.ErrorIs(t, err, keychain.ErrNotFound)
}

func TestStore_Overwrites(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.Store("first"))
	require.NoError(t, keychain.Store("second"))

	got, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, "second", got)
}

func TestDelete_Removes(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.Store("tok-xyz"))
	require.NoError(t, keychain.Delete())

	_, err := keychain.Load()
	assert.ErrorIs(t, err, keychain.ErrNotFound)
}

func TestDelete_WhenEmpty_IsNoOp(t *testing.T) {
	setupMock(t)

	// Deleting when nothing is stored must not error.
	require.NoError(t, keychain.Delete())
}

// ---------------------------------------------------------------------------
// CF Access headless credentials
// ---------------------------------------------------------------------------

func TestStoreCFAccess_And_LoadCFAccess(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.StoreCFAccess("cid-123", "sec-456", "tok-789"))

	gotID, gotSecret, gotToken, err := keychain.LoadCFAccess()
	require.NoError(t, err)
	assert.Equal(t, "cid-123", gotID)
	assert.Equal(t, "sec-456", gotSecret)
	assert.Equal(t, "tok-789", gotToken)
}

func TestLoadCFAccess_NotFound(t *testing.T) {
	setupMock(t)

	_, _, _, err := keychain.LoadCFAccess()
	require.Error(t, err)
	assert.ErrorIs(t, err, keychain.ErrCFAccessNotFound)
}

func TestLoadCFAccess_PartiallyStored(t *testing.T) {
	setupMock(t)

	// Only store one of the three — LoadCFAccess must still fail.
	require.NoError(t, keychain.StoreCFAccess("cid", "sec", "tok"))
	// Delete just the secret to simulate partial state.
	require.NoError(t, keychain.DeleteCFAccess())
	require.NoError(t, gokeyring.Set("argus-cli", "cf-access-client-id", "cid"))

	_, _, _, err := keychain.LoadCFAccess()
	require.Error(t, err)
	assert.ErrorIs(t, err, keychain.ErrCFAccessNotFound)
}

func TestHasCFAccess(t *testing.T) {
	setupMock(t)

	assert.False(t, keychain.HasCFAccess())

	require.NoError(t, keychain.StoreCFAccess("a", "b", "c"))
	assert.True(t, keychain.HasCFAccess())
}

func TestDeleteCFAccess(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.StoreCFAccess("a", "b", "c"))
	require.NoError(t, keychain.DeleteCFAccess())

	assert.False(t, keychain.HasCFAccess())
}

func TestDeleteCFAccess_WhenEmpty_IsNoOp(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.DeleteCFAccess())
}
