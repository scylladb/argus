package services

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
)

const (
	// DefaultSSHKeyTTLSeconds is used when no ttl is provided by the caller.
	DefaultSSHKeyTTLSeconds = 24 * 60 * 60

	// DefaultSSHPrivateKeyName is the default key file name under ~/.ssh.
	DefaultSSHPrivateKeyName = "id_argus_tunnel"

	sshKeyExpiryPrefix = "argus-expiry="
)

var (
	// ErrInvalidSSHKey indicates that a public key file is malformed.
	ErrInvalidSSHKey = errors.New("ssh: invalid public key")

	// ErrSSHBinaryMissing indicates that the local ssh binary was not found.
	ErrSSHBinaryMissing = errors.New("ssh: ssh binary not found")

	// ErrSSHKeygenFailed wraps key-generation failures.
	ErrSSHKeygenFailed = errors.New("ssh: key generation failed")
)

// SSHService implements SSH tunnel-related API and key lifecycle operations.
type SSHService struct {
	client *api.Client
	now    func() time.Time
	runner commandRunner
	lookUp func(file string) (string, error)
}

type commandRunner interface {
	Run(ctx context.Context, name string, args ...string) error
}

type execRunner struct{}

func (execRunner) Run(ctx context.Context, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...) //nolint:gosec // binary and args are fixed by CLI code
	if err := cmd.Run(); err != nil {
		return err
	}
	return nil
}

// SSHServiceOption configures [SSHService].
type SSHServiceOption func(*SSHService)

// WithCommandRunner injects a custom command runner (useful in tests).
func WithCommandRunner(r commandRunner) SSHServiceOption {
	return func(s *SSHService) { s.runner = r }
}

// WithNowFunc injects a custom time source (useful in tests).
func WithNowFunc(now func() time.Time) SSHServiceOption {
	return func(s *SSHService) { s.now = now }
}

// WithLookPathFunc injects a binary lookup function (useful in tests).
func WithLookPathFunc(lookUp func(file string) (string, error)) SSHServiceOption {
	return func(s *SSHService) { s.lookUp = lookUp }
}

// NewSSHService constructs an [SSHService].
func NewSSHService(client *api.Client, opts ...SSHServiceOption) *SSHService {
	s := &SSHService{
		client: client,
		now:    time.Now,
		runner: execRunner{},
		lookUp: exec.LookPath,
	}
	for _, o := range opts {
		o(s)
	}
	return s
}

// KeyState describes the local SSH key material used by the tunnel commands.
type KeyState struct {
	PrivateKeyPath string
	PublicKeyPath  string
	PublicKey      string
	ExpiresAt      time.Time
	HasExpiry      bool
}

// ReadKeyState reads key metadata from private/public key files.
func ReadKeyState(privateKeyPath string) (KeyState, error) {
	priv, err := expandPath(privateKeyPath)
	if err != nil {
		return KeyState{}, err
	}
	pub := priv + ".pub"

	raw, err := os.ReadFile(pub)
	if err != nil {
		return KeyState{}, err
	}

	fields := strings.Fields(strings.TrimSpace(string(raw)))
	if len(fields) < 2 {
		return KeyState{}, ErrInvalidSSHKey
	}

	publicKey := fields[0] + " " + fields[1]
	expiresAt, hasExpiry := parseExpiryFromComment(fields[2:])

	return KeyState{
		PrivateKeyPath: priv,
		PublicKeyPath:  pub,
		PublicKey:      publicKey,
		ExpiresAt:      expiresAt,
		HasExpiry:      hasExpiry,
	}, nil
}

// IsExpired reports whether the key is expired based on its public-key comment.
// Keys without an explicit expiry are treated as expired to force regeneration.
func IsExpired(now time.Time, s KeyState) bool {
	if !s.HasExpiry {
		return true
	}
	return !now.Before(s.ExpiresAt)
}

// EnsureKey makes sure a non-expired key exists at keyPath. When forceRotate
// is true, the key is always re-generated.
func (s *SSHService) EnsureKey(ctx context.Context, keyPath string, ttlSeconds int, forceRotate bool) (KeyState, bool, error) {
	resolved, err := resolveKeyPath(keyPath)
	if err != nil {
		return KeyState{}, false, err
	}

	if !forceRotate {
		if current, readErr := ReadKeyState(resolved); readErr == nil && !IsExpired(s.now().UTC(), current) {
			return current, false, nil
		}
	}

	if err = s.ensureSSHBinary(); err != nil {
		return KeyState{}, false, err
	}

	if ttlSeconds <= 0 {
		ttlSeconds = DefaultSSHKeyTTLSeconds
	}
	expiresAt := s.now().UTC().Add(time.Duration(ttlSeconds) * time.Second)

	if err = generateKeyPair(ctx, s.runner, resolved, expiresAt); err != nil {
		return KeyState{}, false, err
	}

	current, err := ReadKeyState(resolved)
	if err != nil {
		return KeyState{}, false, err
	}

	return current, true, nil
}

// RegisterTunnel uploads a public key and returns tunnel configuration.
func (s *SSHService) RegisterTunnel(
	ctx context.Context,
	publicKey string,
	ttlSeconds int,
	tunnelID string,
) (models.SSHTunnelConfig, error) {
	reqBody := models.SSHTunnelRegisterRequest{
		PublicKey: publicKey,
		TunnelID:  tunnelID,
	}
	if ttlSeconds > 0 {
		reqBody.TTLSeconds = ttlSeconds
	}

	req, err := s.client.NewRequest(ctx, http.MethodPost, api.SSHTunnel, reqBody)
	if err != nil {
		return models.SSHTunnelConfig{}, err
	}

	return api.DoJSON[models.SSHTunnelConfig](s.client, req)
}

// GetTunnelConfig fetches tunnel connection details.
func (s *SSHService) GetTunnelConfig(ctx context.Context, tunnelID string) (models.SSHTunnelConfig, error) {
	route := withTunnelID(api.SSHTunnel, tunnelID)
	req, err := s.client.NewRequest(ctx, http.MethodGet, route, nil)
	if err != nil {
		return models.SSHTunnelConfig{}, err
	}

	return api.DoJSON[models.SSHTunnelConfig](s.client, req)
}

// ListAuthorizedKeys returns the raw authorized_keys payload.
func (s *SSHService) ListAuthorizedKeys(ctx context.Context, tunnelID string) (string, error) {
	route := withTunnelID(api.SSHKeysList, tunnelID)
	req, err := s.client.NewRequest(ctx, http.MethodGet, route, nil)
	if err != nil {
		return "", err
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return "", err
	}
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusUnauthorized {
		return "", fmt.Errorf("%w: server returned %d %s", api.ErrUnauthorized, resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("server returned %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

func withTunnelID(route, tunnelID string) string {
	if strings.TrimSpace(tunnelID) == "" {
		return route
	}
	q := url.Values{}
	q.Set("tunnel_id", tunnelID)
	return route + "?" + q.Encode()
}

// FindFreeLocalPort returns an available local TCP port.
func FindFreeLocalPort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer func() { _ = l.Close() }()
	addr, ok := l.Addr().(*net.TCPAddr)
	if !ok {
		return 0, fmt.Errorf("failed to resolve local TCP address")
	}
	return addr.Port, nil
}

// BuildSSHConnectArgs returns ssh arguments to establish the local tunnel.
func BuildSSHConnectArgs(cfg models.SSHTunnelConfig, privateKeyPath string, localPort int) []string {
	localForward := fmt.Sprintf("127.0.0.1:%d:%s:%d", localPort, cfg.TargetHost, cfg.TargetPort)
	host := fmt.Sprintf("%s@%s", cfg.ProxyUser, cfg.ProxyHost)
	return []string{
		"-N",
		"-L", localForward,
		"-p", strconv.Itoa(cfg.ProxyPort),
		"-i", privateKeyPath,
		"-o", "BatchMode=yes",
		"-o", "ExitOnForwardFailure=yes",
		"-o", "ServerAliveInterval=30",
		"-o", "ServerAliveCountMax=3",
		"-o", "StrictHostKeyChecking=yes",
		host,
	}
}

// WaitForLocalPort waits until local TCP port starts accepting connections.
func WaitForLocalPort(ctx context.Context, port int, timeout time.Duration) error {
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	addr := fmt.Sprintf("127.0.0.1:%d", port)
	for {
		conn, err := net.DialTimeout("tcp", addr, 100*time.Millisecond)
		if err == nil {
			_ = conn.Close()
			return nil
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return fmt.Errorf("timed out waiting for local port %d", port)
		case <-ticker.C:
		}
	}
}

func resolveKeyPath(path string) (string, error) {
	if strings.TrimSpace(path) == "" {
		return DefaultSSHPrivateKeyPath()
	}
	return expandPath(path)
}

// DefaultSSHPrivateKeyPath returns ~/.ssh/id_argus_tunnel.
func DefaultSSHPrivateKeyPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".ssh", DefaultSSHPrivateKeyName), nil
}

func expandPath(path string) (string, error) {
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		path = filepath.Join(home, path[2:])
	}
	return filepath.Abs(path)
}

func (s *SSHService) ensureSSHBinary() error {
	if _, err := s.lookUp("ssh"); err != nil {
		return fmt.Errorf("%w: %w", ErrSSHBinaryMissing, err)
	}
	if _, err := s.lookUp("ssh-keygen"); err != nil {
		return fmt.Errorf("%w: ssh-keygen not found: %w", ErrSSHBinaryMissing, err)
	}
	return nil
}

func generateKeyPair(ctx context.Context, runner commandRunner, privateKeyPath string, expiresAt time.Time) error {
	if err := os.MkdirAll(filepath.Dir(privateKeyPath), 0o700); err != nil {
		return err
	}

	_ = os.Remove(privateKeyPath)
	_ = os.Remove(privateKeyPath + ".pub")

	comment := fmt.Sprintf("%s%d", sshKeyExpiryPrefix, expiresAt.Unix())
	args := []string{
		"-q",
		"-t", "ed25519",
		"-N", "",
		"-f", privateKeyPath,
		"-C", comment,
	}
	if err := runner.Run(ctx, "ssh-keygen", args...); err != nil {
		return fmt.Errorf("%w: %w", ErrSSHKeygenFailed, err)
	}

	if err := os.Chmod(privateKeyPath, 0o600); err != nil {
		return err
	}
	return nil
}

func parseExpiryFromComment(commentFields []string) (time.Time, bool) {
	for _, f := range commentFields {
		if !strings.HasPrefix(f, sshKeyExpiryPrefix) {
			continue
		}
		ts := strings.TrimPrefix(f, sshKeyExpiryPrefix)
		unix, err := strconv.ParseInt(ts, 10, 64)
		if err != nil {
			return time.Time{}, false
		}
		return time.Unix(unix, 0).UTC(), true
	}
	return time.Time{}, false
}
