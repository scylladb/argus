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

// ---- CF token helpers -------------------------------------------------------

func TestStoreCFToken_And_LoadCFToken(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.StoreCFToken("cf-jwt-abc"))

	got, err := keychain.LoadCFToken()
	require.NoError(t, err)
	assert.Equal(t, "cf-jwt-abc", got)
}

func TestLoadCFToken_NotFound(t *testing.T) {
	setupMock(t)

	_, err := keychain.LoadCFToken()
	require.Error(t, err)
	assert.ErrorIs(t, err, keychain.ErrCFTokenNotFound)
}

func TestStoreCFToken_Overwrites(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.StoreCFToken("first-cf"))
	require.NoError(t, keychain.StoreCFToken("second-cf"))

	got, err := keychain.LoadCFToken()
	require.NoError(t, err)
	assert.Equal(t, "second-cf", got)
}

func TestDeleteCFToken_Removes(t *testing.T) {
	setupMock(t)

	require.NoError(t, keychain.StoreCFToken("cf-tok"))
	require.NoError(t, keychain.DeleteCFToken())

	_, err := keychain.LoadCFToken()
	assert.ErrorIs(t, err, keychain.ErrCFTokenNotFound)
}

func TestDeleteCFToken_WhenEmpty_IsNoOp(t *testing.T) {
	setupMock(t)

	// Deleting when nothing is stored must not error.
	require.NoError(t, keychain.DeleteCFToken())
}

func TestCFToken_IndependentFromSession(t *testing.T) {
	setupMock(t)

	// Storing a session must not affect CF token and vice versa.
	require.NoError(t, keychain.Store("session-tok"))
	require.NoError(t, keychain.StoreCFToken("cf-tok"))

	session, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, "session-tok", session)

	cf, err := keychain.LoadCFToken()
	require.NoError(t, err)
	assert.Equal(t, "cf-tok", cf)

	// Deleting one must not affect the other.
	require.NoError(t, keychain.DeleteCFToken())
	_, err = keychain.LoadCFToken()
	assert.ErrorIs(t, err, keychain.ErrCFTokenNotFound)

	session2, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, "session-tok", session2)
}
