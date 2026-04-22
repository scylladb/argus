package models

// SSHTunnelRegisterRequest is the payload accepted by POST /client/ssh/tunnel.
type SSHTunnelRegisterRequest struct {
	PublicKey  string `json:"public_key"`
	TTLSeconds int    `json:"ttl_seconds,omitempty"`
	TunnelID   string `json:"tunnel_id,omitempty"`
}

// SSHTunnelConfig is the tunnel connection payload returned by the SSH tunnel
// API routes.
type SSHTunnelConfig struct {
	KeyID               string `json:"key_id,omitempty"`
	TunnelID            string `json:"tunnel_id"`
	ProxyHost           string `json:"proxy_host"`
	ProxyPort           int    `json:"proxy_port"`
	ProxyUser           string `json:"proxy_user"`
	TargetHost          string `json:"target_host"`
	TargetPort          int    `json:"target_port"`
	HostKnownHostsEntry string `json:"host_key_fingerprint,omitempty"`
	ExpiresAt           string `json:"expires_at,omitempty"`
}
