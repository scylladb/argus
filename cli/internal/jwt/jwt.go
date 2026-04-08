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
	Iat int64 `json:"iat"`
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

// IsOlderThan reports whether the JWT was issued more than maxAge ago.
// It uses the standard "iat" (issued-at) claim for this check.
//
// If the token has no "iat" claim, the function falls back to checking
// whether fewer than maxAge seconds remain before "exp". If there is no
// "exp" claim either, it returns (false, nil) — i.e. cannot determine age.
//
// This is useful for enforcing a maximum cached lifetime independent of what
// the issuer puts in "exp".  For example, capping a CF Access token at 12 h
// even when the token itself has a longer validity period.
func IsOlderThan(tokenStr string, maxAge time.Duration) (bool, error) {
	c, err := parseClaims(tokenStr)
	if err != nil {
		return false, err
	}

	now := time.Now()

	if c.Iat != 0 {
		issued := time.Unix(c.Iat, 0)
		return now.Sub(issued) >= maxAge, nil
	}

	// No iat — fall back: check whether there is less than maxAge left on exp.
	// If exp - now < maxAge, the token was almost certainly issued recently
	// but we can't be sure; treat it as older than maxAge to be safe unless
	// the remaining lifetime still exceeds maxAge (meaning we're early in the
	// token's life).
	if c.Exp != 0 {
		remaining := time.Until(time.Unix(c.Exp, 0))
		// We cannot determine exactly when the token was issued, so compare
		// what's left. If the remaining lifetime is ≤ 0 (expired) or the
		// remaining lifetime is less than we'd expect had the token just been
		// issued, treat it as older than maxAge.
		return remaining <= 0 || remaining < maxAge, nil
	}

	// Cannot determine age — assume not older.
	return false, nil
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
