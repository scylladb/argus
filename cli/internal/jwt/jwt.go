// Package jwt provides lightweight helpers for working with JSON Web Tokens.
// It intentionally avoids signature verification — it is only used to inspect
// claims (e.g. expiry) on tokens that were fetched from trusted sources.
package jwt

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

// Sentinel errors returned by the jwt package.
var (
	// ErrMalformed is returned when the token string does not have the
	// expected three-part dot-separated structure.
	ErrMalformed = errors.New("jwt: malformed token")

	// ErrDecodingPayload is returned when the base64-encoded payload cannot
	// be decoded.
	ErrDecodingPayload = errors.New("jwt: decoding payload")

	// ErrParsingClaims is returned when the payload JSON cannot be unmarshalled.
	ErrParsingClaims = errors.New("jwt: parsing claims")
)

// claims is the minimal set of standard JWT claims we care about.
type claims struct {
	Exp int64 `json:"exp"`
}

// IsExpired reports whether the JWT token string has passed its expiry time.
// It does NOT verify the token signature — callers must only pass tokens that
// were obtained from trusted sources (e.g. directly from cloudflared).
//
// Returns (true, nil) when the token is expired.
// Returns (false, nil) when the token is still valid.
// Returns (false, err) when the token cannot be parsed.
func IsExpired(tokenStr string) (bool, error) {
	c, err := parseClaims(tokenStr)
	if err != nil {
		return false, err
	}
	if c.Exp == 0 {
		// No expiry claim — treat as not expired.
		return false, nil
	}
	return time.Now().Unix() >= c.Exp, nil
}

// parseClaims base64-decodes and JSON-unmarshals the payload segment of a JWT.
func parseClaims(tokenStr string) (claims, error) {
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return claims{}, ErrMalformed
	}

	// JWT payload is base64url-encoded without padding.
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return claims{}, errors.Join(ErrDecodingPayload, err)
	}

	var c claims
	if err := json.Unmarshal(payload, &c); err != nil {
		return claims{}, errors.Join(ErrParsingClaims, err)
	}

	return c, nil
}
