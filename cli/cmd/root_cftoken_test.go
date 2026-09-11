package cmd

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/auth"
	"github.com/scylladb/argus/cli/internal/config"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	gokeyring "github.com/zalando/go-keyring"
)

// testJWT builds a minimal unsigned JWT carrying only exp and iat claims.
func testJWT(exp, iat time.Time) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))
	payload, _ := json.Marshal(map[string]int64{"exp": exp.Unix(), "iat": iat.Unix()})
	return header + "." + base64.RawURLEncoding.EncodeToString(payload) + ".stub-signature"
}

// fakeCloudflaredOnPATH compiles a stub cloudflared binary into a temp dir and
// makes that dir the whole PATH for the test, so
// services.CloudflaredService.Ensure resolves to the stub.
//
//   - `access token …` → prints accessToken and exits 0; exits 1 if it is "".
//   - `access login …` → prints a fake URL line then loginToken and exits 0;
//     exits 1 if loginToken is "" (i.e. a browser login "must not happen").
//
// The test must not call t.Parallel (t.Setenv forbids it).
func fakeCloudflaredOnPATH(t *testing.T, accessToken, loginToken string) {
	t.Helper()

	dir := t.TempDir()
	src := fmt.Sprintf(`package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) >= 3 && os.Args[1] == "access" {
		switch os.Args[2] {
		case "token":
			if %[1]q == "" {
				os.Exit(1)
			}
			fmt.Println(%[1]q)
			os.Exit(0)
		case "login":
			if %[2]q == "" {
				os.Exit(1)
			}
			fmt.Println("A browser window should have opened at the following URL:")
			fmt.Println("https://example.cloudflareaccess.com/cdn-cgi/access/cli?fake=1")
			fmt.Println(%[2]q)
			os.Exit(0)
		}
	}
	os.Exit(0)
}
`, accessToken, loginToken)

	srcFile := filepath.Join(dir, "main.go")
	require.NoError(t, os.WriteFile(srcFile, []byte(src), 0o644))
	out, err := exec.Command("go", "build", "-o", filepath.Join(dir, "cloudflared"), srcFile).CombinedOutput()
	require.NoError(t, err, "building fake cloudflared: %s", out)

	t.Setenv("PATH", dir)
}

// nonInteractiveTestCtx mimics the context PersistentPreRunE hands to
// buildAPIClientRaw under --non-interactive: a logger is mandatory there.
func nonInteractiveTestCtx() context.Context {
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	return contextWithNonInteractive(ctx, true)
}

// cfModeTestEnv isolates the test from the developer's real keychain and
// from any auth-related environment variables.
func cfModeTestEnv(t *testing.T) {
	t.Helper()
	gokeyring.MockInit()
	withRootTestEnv(t, false, map[string]string{
		"ARGUS_AUTH_TOKEN":              "pat-from-env",
		"ARGUS_TOKEN":                   "",
		"ARGUS_CF_ACCESS_CLIENT_ID":     "",
		"ARGUS_CF_ACCESS_CLIENT_SECRET": "",
		"ARGUS_DISABLE_CLOUDFLARE":      "",
	})
}

// TestEnsureCFToken_NonInteractive_AcceptsStaleButUnexpiredToken pins the
// regression from the 2026-09 investigation: with --non-interactive, a cached
// CF token older than auth.CFTokenMaxAge but not yet past "exp" must be used
// as-is (Cloudflare still honours it) rather than dropped.
func TestEnsureCFToken_NonInteractive_AcceptsStaleButUnexpiredToken(t *testing.T) {
	now := time.Now()
	stale := testJWT(now.Add(11*time.Hour), now.Add(-13*time.Hour))
	fakeCloudflaredOnPATH(t, stale, "") // access login must not be attempted

	got, err := ensureCFToken(context.Background(), "https://argus.example.com", false)
	require.NoError(t, err)
	assert.Equal(t, stale, got)
}

func TestEnsureCFToken_NonInteractive_ExpiredTokenIsAnError(t *testing.T) {
	now := time.Now()
	expired := testJWT(now.Add(-time.Minute), now.Add(-24*time.Hour))
	fresh := testJWT(now.Add(24*time.Hour), now)
	fakeCloudflaredOnPATH(t, expired, fresh) // login would work, but must not be used non-interactively

	_, err := ensureCFToken(context.Background(), "https://argus.example.com", false)
	require.ErrorIs(t, err, auth.ErrCFTokenExpired)
	assert.Contains(t, err.Error(), "argus auth")
}

// TestEnsureCFToken_Interactive_StaleTokenIsRefreshed documents the
// intentional asymmetry: interactively, a stale token is refreshed through
// the cloudflared login flow instead of being reused.
func TestEnsureCFToken_Interactive_StaleTokenIsRefreshed(t *testing.T) {
	now := time.Now()
	stale := testJWT(now.Add(11*time.Hour), now.Add(-13*time.Hour))
	fresh := testJWT(now.Add(24*time.Hour), now)
	fakeCloudflaredOnPATH(t, stale, fresh)

	got, err := ensureCFToken(context.Background(), "https://argus.example.com", true)
	require.NoError(t, err)
	assert.Equal(t, fresh, got)
}

func TestBuildAPIClientRaw_NonInteractive_StaleTokenAttachedAsCookie(t *testing.T) {
	cfModeTestEnv(t)
	now := time.Now()
	stale := testJWT(now.Add(11*time.Hour), now.Add(-13*time.Hour))
	fakeCloudflaredOnPATH(t, stale, "")

	ctx := nonInteractiveTestCtx()
	cfg := &config.Config{URL: "https://argus.example.com", UseCf: true}
	client, err := buildAPIClientRaw(ctx, cfg)
	require.NoError(t, err)

	req, err := client.NewRequest(ctx, http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)
	c, err := req.Cookie("CF_Authorization")
	require.NoError(t, err)
	assert.Equal(t, stale, c.Value)
}

// TestBuildAPIClientRaw_NonInteractive_ExpiredTokenFailsFastWithCause verifies
// that when no CF token can be obtained, the first API call fails with the
// real cause instead of the misleading "text/html" error, and that no
// unauthenticated request is sent at all.
func TestBuildAPIClientRaw_NonInteractive_ExpiredTokenFailsFastWithCause(t *testing.T) {
	cfModeTestEnv(t)
	now := time.Now()
	fakeCloudflaredOnPATH(t, testJWT(now.Add(-time.Minute), now.Add(-24*time.Hour)), "")

	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits.Add(1)
		w.Header().Set("Content-Type", "text/html")
		_, _ = io.WriteString(w, "<html>Cloudflare Access login</html>")
	}))
	t.Cleanup(srv.Close)

	ctx := nonInteractiveTestCtx()
	cfg := &config.Config{URL: srv.URL, UseCf: true}
	client, err := buildAPIClientRaw(ctx, cfg)
	require.NoError(t, err, "client must still be built so non-API commands keep working")

	req, err := client.NewRequest(ctx, http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)
	_, err = api.DoJSON[map[string]any](client, req)
	require.ErrorIs(t, err, api.ErrUnauthorized)
	require.ErrorIs(t, err, auth.ErrCFTokenExpired)
	assert.NotContains(t, err.Error(), "text/html")
	assert.Equal(t, int32(0), hits.Load(), "no unauthenticated request must be sent")
}

// TestBuildAPIClientRaw_NonInteractive_ServiceTokenEnvIsNotBlocked verifies
// that a CF Access service token from the environment is an acceptable
// substitute for the browser-login JWT: no fail-fast error is recorded.
func TestBuildAPIClientRaw_NonInteractive_ServiceTokenEnvIsNotBlocked(t *testing.T) {
	gokeyring.MockInit()
	withRootTestEnv(t, false, map[string]string{
		"ARGUS_AUTH_TOKEN":              "pat-from-env",
		"ARGUS_TOKEN":                   "",
		"ARGUS_CF_ACCESS_CLIENT_ID":     "cf-id",
		"ARGUS_CF_ACCESS_CLIENT_SECRET": "cf-secret",
		"ARGUS_DISABLE_CLOUDFLARE":      "",
	})
	now := time.Now()
	fakeCloudflaredOnPATH(t, testJWT(now.Add(-time.Minute), now.Add(-24*time.Hour)), "")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "cf-id", r.Header.Get("CF-Access-Client-Id"))
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ok","response":{"v":"1"}}`)
	}))
	t.Cleanup(srv.Close)

	ctx := nonInteractiveTestCtx()
	cfg := &config.Config{URL: srv.URL, UseCf: true}
	client, err := buildAPIClientRaw(ctx, cfg)
	require.NoError(t, err)

	req, err := client.NewRequest(ctx, http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)
	got, err := api.DoJSON[map[string]string](client, req)
	require.NoError(t, err)
	assert.Equal(t, "1", got["v"])
}
