package jwt_test

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/scylladb/argus/cli/internal/jwt"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// makeToken builds a minimal unsigned JWT with the given exp Unix timestamp.
// The header and signature segments are stubs — IsExpired only reads the payload.
func makeToken(exp int64) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))

	type payload struct {
		Exp int64 `json:"exp"`
	}
	raw, _ := json.Marshal(payload{Exp: exp})
	payloadB64 := base64.RawURLEncoding.EncodeToString(raw)

	return fmt.Sprintf("%s.%s.stub-signature", header, payloadB64)
}

func TestIsExpired_NotExpired(t *testing.T) {
	tok := makeToken(time.Now().Add(time.Hour).Unix())

	expired, err := jwt.IsExpired(tok)
	require.NoError(t, err)
	assert.False(t, expired, "token with future exp should not be expired")
}

func TestIsExpired_Expired(t *testing.T) {
	tok := makeToken(time.Now().Add(-time.Hour).Unix())

	expired, err := jwt.IsExpired(tok)
	require.NoError(t, err)
	assert.True(t, expired, "token with past exp should be expired")
}

func TestIsExpired_NoExpClaim(t *testing.T) {
	// Payload with no exp field.
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))
	payloadB64 := base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"user"}`))
	tok := fmt.Sprintf("%s.%s.stub", header, payloadB64)

	expired, err := jwt.IsExpired(tok)
	require.NoError(t, err)
	assert.False(t, expired, "token without exp claim should not be treated as expired")
}

func TestIsExpired_MalformedToken(t *testing.T) {
	_, err := jwt.IsExpired("not.a.valid.jwt.at.all")
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrMalformed)
}

func TestIsExpired_BadBase64(t *testing.T) {
	tok := "header.!!!not-base64!!!.sig"
	_, err := jwt.IsExpired(tok)
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrDecodingPayload)
}

func TestIsExpired_BadJSON(t *testing.T) {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256"}`))
	badPayload := base64.RawURLEncoding.EncodeToString([]byte(`not json`))
	tok := strings.Join([]string{header, badPayload, "sig"}, ".")

	_, err := jwt.IsExpired(tok)
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrParsingClaims)
}

// --------------------------------------------------------------------------
// Edge cases added for fuller coverage
// --------------------------------------------------------------------------

// TestIsExpired_EmptyString verifies that an empty string returns ErrMalformed
// (it has only 1 part when split on ".").
func TestIsExpired_EmptyString(t *testing.T) {
	t.Parallel()

	_, err := jwt.IsExpired("")
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrMalformed)
}

// TestIsExpired_TwoParts verifies that a token with exactly two dots-separated
// parts returns ErrMalformed (a valid JWT has exactly three parts).
func TestIsExpired_TwoParts(t *testing.T) {
	t.Parallel()

	_, err := jwt.IsExpired("a.b")
	require.Error(t, err)
	assert.ErrorIs(t, err, jwt.ErrMalformed)
}

// TestIsExpired_ExpZeroExplicit verifies that a token whose payload explicitly
// sets "exp":0 is treated as not expired (same as a missing exp claim).
func TestIsExpired_ExpZeroExplicit(t *testing.T) {
	t.Parallel()

	tok := makeToken(0)

	expired, err := jwt.IsExpired(tok)
	require.NoError(t, err)
	assert.False(t, expired, `explicit "exp":0 should be treated as no expiry (not expired)`)
}

// TestIsExpired_ExactBoundary verifies the boundary condition: a token whose
// exp equals exactly time.Now().Unix() is considered expired (>= comparison).
func TestIsExpired_ExactBoundary(t *testing.T) {
	t.Parallel()

	// Capture now before building the token so the comparison is tight.
	now := time.Now().Unix()
	tok := makeToken(now)

	expired, err := jwt.IsExpired(tok)
	require.NoError(t, err)
	assert.True(t, expired, "token whose exp == now should be considered expired")
}
