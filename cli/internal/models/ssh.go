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
	// Proxies lists every active proxy, best choice first, so a client can fail
	// over locally instead of giving up. Empty against an older backend.
	Proxies []SSHTunnelConfig `json:"proxies,omitempty"`
}

// Candidates returns the proxies to try in order: this one, then every
// failover proxy the backend offered.
func (c SSHTunnelConfig) Candidates() []SSHTunnelConfig {
	candidates := []SSHTunnelConfig{c}
	for _, proxy := range c.Proxies {
		if proxy.ProxyHost == c.ProxyHost && proxy.ProxyPort == c.ProxyPort {
			continue
		}
		proxy.KeyID = c.KeyID
		proxy.ExpiresAt = c.ExpiresAt
		proxy.Proxies = nil
		candidates = append(candidates, proxy)
	}
	return candidates
}
