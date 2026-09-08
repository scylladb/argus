package models

import "time"

// Version contains version control commit id
type Version struct {
	CommitId string `json:"commit_id"`
}

func (Version) Headers() []string {
	return []string{"Commit Id"}
}

func (v Version) Rows() [][]string {
	return [][]string{{v.CommitId}}
}

// UserTokenRequest is the body of POST /api/v1/user/token. Duration is a
// human-readable lifetime such as "14d" or "24h"; the server defaults to 365d
// when the body is omitted.
type UserTokenRequest struct {
	Duration string `json:"duration"`
}

// UserTokenResponse is the payload of POST /api/v1/user/token.
type UserTokenResponse struct {
	Token string `json:"token"`
	// ExpirationDate is nil for a non-expiring token.
	ExpirationDate *time.Time `json:"expiration_date"`
}

// UserTokenInfo is the payload of GET /api/v1/user/token: the expiration of
// the token that authenticated the request (nil when it never expires).
type UserTokenInfo struct {
	ExpirationDate *time.Time `json:"expiration_date"`
}
