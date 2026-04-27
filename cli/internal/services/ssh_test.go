package services_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type fakeRunner struct {
	calls [][]string
}

func (r *fakeRunner) Run(_ context.Context, name string, args ...string) error {
	r.calls = append(r.calls, append([]string{name}, args...))
	if name != "ssh-keygen" {
		return nil
	}

	path := ""
	comment := ""
	for i := 0; i < len(args)-1; i++ {
		if args[i] == "-f" {
			path = args[i+1]
		}
		if args[i] == "-C" {
			comment = args[i+1]
		}
	}
	if path == "" {
		return fmt.Errorf("missing -f arg")
	}

	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	if err := os.WriteFile(path, []byte("PRIVATE"), 0o600); err != nil {
		return err
	}
	pub := "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakePublicKey " + comment + "\n"
	return os.WriteFile(path+".pub", []byte(pub), 0o644)
}

func okEnvelope(t *testing.T, payload any) []byte {
	t.Helper()
	raw, err := json.Marshal(payload)
	require.NoError(t, err)
	env := map[string]json.RawMessage{
		"status":   json.RawMessage(`"ok"`),
		"response": raw,
	}
	b, err := json.Marshal(env)
	require.NoError(t, err)
	return b
}

func TestEnsureKey_GeneratesAndParsesExpiry(t *testing.T) {
	t.Parallel()

	now := time.Unix(1_700_000_000, 0).UTC()
	runner := &fakeRunner{}
	lookUp := func(_ string) (string, error) { return "/usr/bin/ok", nil }

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)
	svc := services.NewSSHService(
		client,
		services.WithNowFunc(func() time.Time { return now }),
		services.WithCommandRunner(runner),
		services.WithLookPathFunc(lookUp),
	)

	keyPath := filepath.Join(t.TempDir(), "id_argus_tunnel")
	state, rotated, err := svc.EnsureKey(context.Background(), keyPath, 3600, false)
	require.NoError(t, err)
	assert.True(t, rotated)
	assert.True(t, state.HasExpiry)
	assert.Equal(t, now.Add(3600*time.Second), state.ExpiresAt)
	assert.FileExists(t, keyPath)
	assert.FileExists(t, keyPath+".pub")
	require.Len(t, runner.calls, 1)
	assert.Equal(t, "ssh-keygen", runner.calls[0][0])
}

func TestEnsureKey_ReusesUnexpiredKey(t *testing.T) {
	t.Parallel()

	now := time.Unix(1_700_000_000, 0).UTC()
	exp := now.Add(10 * time.Minute).Unix()
	keyPath := filepath.Join(t.TempDir(), "id_argus_tunnel")
	require.NoError(t, os.WriteFile(keyPath, []byte("PRIVATE"), 0o600))
	pub := fmt.Sprintf("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake argus-expiry=%d\n", exp)
	require.NoError(t, os.WriteFile(keyPath+".pub", []byte(pub), 0o644))

	runner := &fakeRunner{}
	lookUp := func(_ string) (string, error) { return "/usr/bin/ok", nil }

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)
	svc := services.NewSSHService(
		client,
		services.WithNowFunc(func() time.Time { return now }),
		services.WithCommandRunner(runner),
		services.WithLookPathFunc(lookUp),
	)

	state, rotated, err := svc.EnsureKey(context.Background(), keyPath, 3600, false)
	require.NoError(t, err)
	assert.False(t, rotated)
	assert.Equal(t, now.Add(10*time.Minute), state.ExpiresAt)
	assert.Empty(t, runner.calls)
}

func TestEnsureKey_ExpiredForcesRegenerate(t *testing.T) {
	t.Parallel()

	now := time.Unix(1_700_000_000, 0).UTC()
	exp := now.Add(-10 * time.Minute).Unix()
	keyPath := filepath.Join(t.TempDir(), "id_argus_tunnel")
	require.NoError(t, os.WriteFile(keyPath, []byte("PRIVATE"), 0o600))
	pub := fmt.Sprintf("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake argus-expiry=%d\n", exp)
	require.NoError(t, os.WriteFile(keyPath+".pub", []byte(pub), 0o644))

	runner := &fakeRunner{}
	lookUp := func(_ string) (string, error) { return "/usr/bin/ok", nil }

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)
	svc := services.NewSSHService(
		client,
		services.WithNowFunc(func() time.Time { return now }),
		services.WithCommandRunner(runner),
		services.WithLookPathFunc(lookUp),
	)

	_, rotated, err := svc.EnsureKey(context.Background(), keyPath, 3600, false)
	require.NoError(t, err)
	assert.True(t, rotated)
	require.Len(t, runner.calls, 1)
}

func TestEnsureKey_MissingSSHBinary(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)
	svc := services.NewSSHService(
		client,
		services.WithLookPathFunc(func(_ string) (string, error) {
			return "", errors.New("not found")
		}),
	)

	_, _, err = svc.EnsureKey(context.Background(), filepath.Join(t.TempDir(), "k"), 3600, true)
	require.Error(t, err)
	assert.ErrorIs(t, err, services.ErrSSHBinaryMissing)
}

func TestRegisterTunnel_UsesExpectedRouteAndBody(t *testing.T) {
	t.Parallel()

	var gotPath string
	var gotMethod string
	var gotBody models.SSHTunnelRegisterRequest

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotMethod = r.Method
		require.NoError(t, json.NewDecoder(r.Body).Decode(&gotBody))
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(okEnvelope(t, models.SSHTunnelConfig{TunnelID: "tid", ProxyHost: "h", ProxyPort: 22, ProxyUser: "u", TargetHost: "t", TargetPort: 8080}))
	}))
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	svc := services.NewSSHService(client)
	_, err = svc.RegisterTunnel(context.Background(), "ssh-ed25519 AAAA", 7200, "tun-1")
	require.NoError(t, err)

	assert.Equal(t, http.MethodPost, gotMethod)
	assert.Equal(t, api.SSHTunnel, gotPath)
	assert.Equal(t, "ssh-ed25519 AAAA", gotBody.PublicKey)
	assert.Equal(t, 7200, gotBody.TTLSeconds)
	assert.Equal(t, "tun-1", gotBody.TunnelID)
}

func TestGetTunnelConfig_UsesTunnelIDQuery(t *testing.T) {
	t.Parallel()

	var gotRawQuery string

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotRawQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(okEnvelope(t, models.SSHTunnelConfig{TunnelID: "tid", ProxyHost: "h", ProxyPort: 22, ProxyUser: "u", TargetHost: "t", TargetPort: 8080}))
	}))
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	svc := services.NewSSHService(client)

	_, err = svc.GetTunnelConfig(context.Background(), "tun-123")
	require.NoError(t, err)
	assert.Equal(t, "tunnel_id=tun-123", gotRawQuery)
}

func TestListAuthorizedKeys_ReturnsRawBody(t *testing.T) {
	t.Parallel()

	const keys = "ssh-ed25519 AAAA key1\nssh-ed25519 BBBB key2\n"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte(keys))
	}))
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	svc := services.NewSSHService(client)

	got, err := svc.ListAuthorizedKeys(context.Background(), "")
	require.NoError(t, err)
	assert.Equal(t, keys, got)
}

func TestBuildSSHConnectArgs_EnablesStrictHostKeyChecking(t *testing.T) {
	t.Parallel()

	args := services.BuildSSHConnectArgs(models.SSHTunnelConfig{
		ProxyHost:  "proxy.example.com",
		ProxyPort:  22,
		ProxyUser:  "argus-proxy",
		TargetHost: "10.0.0.5",
		TargetPort: 8080,
	}, "/tmp/id_argus_tunnel", 43210, "/tmp/argus-known-hosts")

	joined := strings.Join(args, " ")
	assert.Contains(t, joined, "StrictHostKeyChecking=yes")
	assert.Contains(t, joined, "UserKnownHostsFile=/tmp/argus-known-hosts")
	assert.Contains(t, joined, "-L 127.0.0.1:43210:10.0.0.5:8080")
	assert.Contains(t, joined, "argus-proxy@proxy.example.com")
}

func TestPrepareKnownHostsFile_WritesMatchingKey(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	svc := services.NewSSHService(client)
	entry := "[proxy.example.com]:2222 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMockKey"

	path, err := svc.PrepareKnownHostsFile(context.Background(), models.SSHTunnelConfig{
		HostKnownHostsEntry: entry,
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = os.Remove(path)
	})

	raw, err := os.ReadFile(path)
	require.NoError(t, err)
	assert.Equal(t, entry+"\n", string(raw))

	stat, err := os.Stat(path)
	require.NoError(t, err)
	assert.Equal(t, os.FileMode(0o600), stat.Mode().Perm())
}

func TestPrepareKnownHostsFile_ReturnsEmptyPathForMissingFingerprint(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	svc := services.NewSSHService(client)

	// Empty / missing entry falls back gracefully (StrictHostKeyChecking=no).
	path, err := svc.PrepareKnownHostsFile(context.Background(), models.SSHTunnelConfig{
		HostKnownHostsEntry: "   ",
	})
	require.NoError(t, err)
	assert.Empty(t, path)
}

func TestPrepareKnownHostsFile_ReturnsEmptyPathForRawSHA256Fingerprint(t *testing.T) {
	t.Parallel()

	client, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	svc := services.NewSSHService(client)

	// Raw SHA256 fingerprint (old backend) falls back gracefully.
	path, err := svc.PrepareKnownHostsFile(context.Background(), models.SSHTunnelConfig{
		HostKnownHostsEntry: "SHA256:abc123",
	})
	require.NoError(t, err)
	assert.Empty(t, path)
}

func TestFindFreeLocalPortAndWaitForLocalPort(t *testing.T) {
	t.Parallel()

	port, err := services.FindFreeLocalPort()
	require.NoError(t, err)
	require.NotZero(t, port)

	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	require.NoError(t, err)
	defer func() { _ = ln.Close() }()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	require.NoError(t, services.WaitForLocalPort(ctx, port, 2*time.Second))
}
