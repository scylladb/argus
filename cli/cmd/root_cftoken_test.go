package cmd

import (
	"bytes"
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

// testJWT builds a minimal unsigned JWT carrying exp and iat claims.
func testJWT(t *testing.T, exp, iat time.Time) string {
	t.Helper()
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))
	payload, err := json.Marshal(map[string]int64{"exp": exp.Unix(), "iat": iat.Unix()})
	require.NoError(t, err)
	return header + "." + base64.RawURLEncoding.EncodeToString(payload) + ".stub-signature"
}

// fakeCloudflaredOnPATH puts a stub cloudflared first on PATH. `access token`
// prints accessToken, `access login` prints loginToken; an empty value makes
// that subcommand exit 1. Not compatible with t.Parallel (t.Setenv).
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

func nonInteractiveTestCtx() context.Context {
	ctx := contextWithLogger(context.Background(), zerolog.Nop())
	return contextWithNonInteractive(ctx, true)
}

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

// Regression: with --non-interactive, an old cached token that is still
// valid must be used as-is rather than dropped.
func TestEnsureCFToken_NonInteractive_AcceptsOldValidToken(t *testing.T) {
	now := time.Now()
	old := testJWT(t, now.Add(11*time.Hour), now.Add(-13*time.Hour))
	fakeCloudflaredOnPATH(t, old, "") // access login must not be attempted

	got, err := ensureCFToken(context.Background(), "https://argus.example.com", false)
	require.NoError(t, err)
	assert.Equal(t, old, got)
}

func TestEnsureCFToken_NonInteractive_ExpiringTokenIsUsedWithWarning(t *testing.T) {
	now := time.Now()
	expiring := testJWT(t, now.Add(time.Minute), now.Add(-24*time.Hour))
	fakeCloudflaredOnPATH(t, expiring, "")

	var logs bytes.Buffer
	ctx := contextWithLogger(context.Background(), zerolog.New(&logs))
	got, err := ensureCFToken(ctx, "https://argus.example.com", false)
	require.NoError(t, err)
	assert.Equal(t, expiring, got)
	assert.Contains(t, logs.String(), "about to expire")
}

func TestEnsureCFToken_NonInteractive_ExpiredTokenIsAnError(t *testing.T) {
	now := time.Now()
	expired := testJWT(t, now.Add(-time.Minute), now.Add(-24*time.Hour))
	fresh := testJWT(t, now.Add(24*time.Hour), now)
	fakeCloudflaredOnPATH(t, expired, fresh) // login would work, but must not be used non-interactively

	_, err := ensureCFToken(context.Background(), "https://argus.example.com", false)
	require.ErrorIs(t, err, auth.ErrCFTokenExpired)
	assert.Contains(t, err.Error(), "argus auth")
}

func TestEnsureCFToken_Interactive_ExpiringTokenIsRefreshed(t *testing.T) {
	t.Setenv("HOME", t.TempDir()) // keep dropCachedCFToken away from the real cache
	now := time.Now()
	expiring := testJWT(t, now.Add(time.Minute), now.Add(-24*time.Hour))
	fresh := testJWT(t, now.Add(24*time.Hour), now)
	fakeCloudflaredOnPATH(t, expiring, fresh)

	got, err := ensureCFToken(context.Background(), "https://argus.example.com", true)
	require.NoError(t, err)
	assert.Equal(t, fresh, got)
}

func TestBuildAPIClientRaw_NonInteractive_OldValidTokenAttachedAsCookie(t *testing.T) {
	cfModeTestEnv(t)
	now := time.Now()
	old := testJWT(t, now.Add(11*time.Hour), now.Add(-13*time.Hour))
	fakeCloudflaredOnPATH(t, old, "")

	ctx := nonInteractiveTestCtx()
	cfg := &config.Config{URL: "https://argus.example.com", UseCf: true}
	client, err := buildAPIClientRaw(ctx, cfg)
	require.NoError(t, err)

	req, err := client.NewRequest(ctx, http.MethodGet, "/api/v1/version", nil)
	require.NoError(t, err)
	c, err := req.Cookie("CF_Authorization")
	require.NoError(t, err)
	assert.Equal(t, old, c.Value)
}

func TestBuildAPIClientRaw_NonInteractive_ExpiredTokenFailsFastWithCause(t *testing.T) {
	cfModeTestEnv(t)
	now := time.Now()
	fakeCloudflaredOnPATH(t, testJWT(t, now.Add(-time.Minute), now.Add(-24*time.Hour)), "")

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
	fakeCloudflaredOnPATH(t, testJWT(t, now.Add(-time.Minute), now.Add(-24*time.Hour)), "")

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
