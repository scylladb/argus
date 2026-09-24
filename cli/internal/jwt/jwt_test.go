package jwt_test

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/scylladb/argus/cli/internal/jwt"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// makeToken builds a minimal unsigned JWT with the given exp Unix timestamp.
// The header and signature segments are stubs — ExpiresAt only reads the payload.
func makeToken(exp int64) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))

	type payload struct {
		Exp int64 `json:"exp"`
	}
	raw, _ := json.Marshal(payload{Exp: exp})
	payloadB64 := base64.RawURLEncoding.EncodeToString(raw)

	return fmt.Sprintf("%s.%s.stub-signature", header, payloadB64)
}

func TestExpiresAt(t *testing.T) {
	exp := time.Now().Add(time.Hour).Truncate(time.Second)
	got, err := jwt.ExpiresAt(makeToken(exp.Unix()))
	require.NoError(t, err)
	assert.True(t, got.Equal(exp))
}

func TestExpiresAt_NoExpClaim(t *testing.T) {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"none"}`))
	payload := base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"x"}`))
	got, err := jwt.ExpiresAt(header + "." + payload + ".sig")
	require.NoError(t, err)
	assert.True(t, got.IsZero())
}

func TestExpiresAt_ExpZeroIsNoExpiry(t *testing.T) {
	got, err := jwt.ExpiresAt(makeToken(0))
	require.NoError(t, err)
	assert.True(t, got.IsZero())
}

func TestExpiresAt_InvalidToken(t *testing.T) {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256"}`))
	notJSON := base64.RawURLEncoding.EncodeToString([]byte(`not json`))

	for name, tc := range map[string]struct {
		token string
		want  error
	}{
		"empty":       {"", jwt.ErrMalformed},
		"one part":    {"nope", jwt.ErrMalformed},
		"two parts":   {"a.b", jwt.ErrMalformed},
		"six parts":   {"not.a.valid.jwt.at.all", jwt.ErrMalformed},
		"bad base64":  {"header.!!!not-base64!!!.sig", jwt.ErrDecodingPayload},
		"bad payload": {header + "." + notJSON + ".sig", jwt.ErrParsingClaims},
	} {
		t.Run(name, func(t *testing.T) {
			_, err := jwt.ExpiresAt(tc.token)
			assert.ErrorIs(t, err, tc.want)
		})
	}
}
