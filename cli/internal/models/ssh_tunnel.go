package models

import "time"

// ProxyTunnelConfig is the DTO returned by the admin proxy-tunnel endpoints.
type ProxyTunnelConfig struct {
	ID                 string  `json:"id"`
	Host               string  `json:"host"`
	Port               int     `json:"port"`
	ProxyUser          string  `json:"proxy_user"`
	TargetHost         string  `json:"target_host"`
	TargetPort         int     `json:"target_port"`
	HostKeyFingerprint string  `json:"host_key_fingerprint"`
	ServiceUserID      *string `json:"service_user_id"`
	IsActive           bool    `json:"is_active"`
	// APIToken is only populated on create / re-provision responses.
	APIToken *string `json:"api_token"`
}

// ProxyTunnelCreatePayload is the request body for POST /admin/api/v1/proxy-tunnel/config.
type ProxyTunnelCreatePayload struct {
	Host       string `json:"host"`
	Port       int    `json:"port"`
	ProxyUser  string `json:"proxy_user"`
	TargetHost string `json:"target_host"`
	TargetPort int    `json:"target_port"`
	IsActive   bool   `json:"is_active"`
}

// ProxyTunnelActivePayload is the request body for POST /admin/api/v1/proxy-tunnel/config/{id}/active.
type ProxyTunnelActivePayload struct {
	IsActive bool `json:"is_active"`
}

// SSHTunnelKey is the DTO returned by GET /admin/api/v1/ssh/keys.
type SSHTunnelKey struct {
	KeyID       string    `json:"key_id"`
	UserID      string    `json:"user_id"`
	TunnelID    string    `json:"tunnel_id"`
	Fingerprint string    `json:"fingerprint"`
	CreatedAt   time.Time `json:"created_at"`
	ExpiresAt   time.Time `json:"expires_at"`
}
