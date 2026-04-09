package auth_test

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	gokeyring "github.com/zalando/go-keyring"

	"github.com/scylladb/argus/cli/internal/auth"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// setupMockKeyring installs the in-memory keyring provider for the duration
// of the test, ensuring tests never touch the real OS keychain.
func setupMockKeyring(t *testing.T) {
	t.Helper()
	gokeyring.MockInit()
}

// fakeCFBin compiles a tiny Go program that behaves as a stub cloudflared
// binary for testing both the `access login` and `access token` subcommands.
//
//   - `access login …`  → prints a fake browser URL line then the token on the
//     last line, exits with loginExit.
//   - `access token …`  → prints the token and exits with tokenExit.
//   - anything else     → exits 0 silently.
func fakeCFBin(t *testing.T, token string, loginExit, tokenExit int) string {
	t.Helper()

	dir := t.TempDir()
	binPath := filepath.Join(dir, "cloudflared")

	src := fmt.Sprintf(`package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) >= 3 && os.Args[1] == "access" {
		switch os.Args[2] {
		case "login":
			// Simulate cloudflared access login output: URL line then JWT.
			fmt.Println("A browser window should have opened at the following URL:")
			fmt.Println("https://example.cloudflareaccess.com/cdn-cgi/access/cli?fake=1")
			fmt.Println(%q)
			os.Exit(%d)
		case "token":
			fmt.Println(%q)
			os.Exit(%d)
		}
	}
	os.Exit(0)
}
`, token, loginExit, token, tokenExit)

	srcFile := filepath.Join(dir, "main.go")
	require.NoError(t, os.WriteFile(srcFile, []byte(src), 0o644))

	out, err := exec.Command("go", "build", "-o", binPath, srcFile).CombinedOutput()
	require.NoError(t, err, "failed to build fake cloudflared: %s", out)

	return binPath
}

// fakeCFBinDualToken compiles a stub cloudflared binary where:
//   - `access token …` → prints tokenForAccess and exits 0.
//   - `access login …` → prints loginToken (with a fake URL line) and exits 0.
//
// This is used to test the flow where `access token` returns an expired JWT
// and `access login` must provide a fresh one.
func fakeCFBinDualToken(t *testing.T, tokenForAccess, loginToken string) string {
	t.Helper()

	dir := t.TempDir()
	binPath := filepath.Join(dir, "cloudflared")

	src := fmt.Sprintf(`package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) >= 3 && os.Args[1] == "access" {
		switch os.Args[2] {
		case "login":
			fmt.Println("A browser window should have opened at the following URL:")
			fmt.Println("https://example.cloudflareaccess.com/cdn-cgi/access/cli?fake=1")
			fmt.Println(%q)
			os.Exit(0)
		case "token":
			fmt.Println(%q)
			os.Exit(0)
		}
	}
	os.Exit(0)
}
`, loginToken, tokenForAccess)

	srcFile := filepath.Join(dir, "main.go")
	require.NoError(t, os.WriteFile(srcFile, []byte(src), 0o644))

	out, err := exec.Command("go", "build", "-o", binPath, srcFile).CombinedOutput()
	require.NoError(t, err, "failed to build fake cloudflared: %s", out)

	return binPath
}

// makeJWT builds a minimal unsigned JWT with the given exp and iat Unix
// timestamps. The header and signature are stubs — only the payload matters
// for our tests. Pass iat=0 to omit the iat claim.
func makeJWT(exp, iat int64) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))

	type payload struct {
		Sub string `json:"sub"`
		Exp int64  `json:"exp"`
		Iat int64  `json:"iat,omitempty"`
	}
	raw, _ := json.Marshal(payload{Sub: "testuser", Exp: exp, Iat: iat})
	payloadB64 := base64.RawURLEncoding.EncodeToString(raw)

	return fmt.Sprintf("%s.%s.stub-signature", header, payloadB64)
}

// validJWT returns a JWT with an expiry 13 hours in the future and an iat of
// now, so it passes the 12 h maximum-age cap enforced by IsOlderThan.
func validJWT() string {
	now := time.Now()
	return makeJWT(now.Add(13*time.Hour).Unix(), now.Unix())
}

// expiredJWT returns a JWT with an expiry one hour in the past.
func expiredJWT() string { return makeJWT(time.Now().Add(-time.Hour).Unix(), 0) }

// userTokenJSON returns a JSON body that mimics the /api/v1/user/token response.
func userTokenJSON(token string) []byte {
	type inner struct {
		Token string `json:"token"`
	}
	type envelope struct {
		Status   string `json:"status"`
		Response inner  `json:"response"`
	}
	b, _ := json.Marshal(envelope{Status: "ok", Response: inner{Token: token}})
	return b
}

// newArgusTestServer creates an httptest.Server that handles both the CF login
// endpoint and the user-token endpoint used by the PAT exchange step.
//
//   - POST /auth/login/cf with the expected CF JWT → sets a session cookie.
//   - GET  /api/v1/user/token with a valid session → returns patToken as JSON.
//   - Everything else → 404.
func newArgusTestServer(t *testing.T, cfJWT, sessionValue, patToken string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/auth/login/cf":
			c, err := r.Cookie("CF_Authorization")
			if err != nil || c.Value != cfJWT {
				http.Error(w, "missing or wrong CF_Authorization cookie", http.StatusBadRequest)
				return
			}
			http.SetCookie(w, &http.Cookie{Name: "session", Value: sessionValue})
			w.WriteHeader(http.StatusOK)

		case r.Method == http.MethodGet && r.URL.Path == "/api/v1/user/token":
			// Verify the session cookie is present.
			c, err := r.Cookie("session")
			if err != nil || c.Value != sessionValue {
				http.Error(w, "missing or wrong session cookie", http.StatusUnauthorized)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write(userTokenJSON(patToken))

		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

// ---- tests -----------------------------------------------------------------

// TestArgusService_Login_OverwritesCachedPAT verifies that Login always
// performs the full cloudflared flow even when a PAT is already stored in
// the keychain, replacing the old PAT with a freshly obtained one.
func TestArgusService_Login_OverwritesCachedPAT(t *testing.T) {
	setupMockKeyring(t)
	require.NoError(t, keychain.StorePAT("stale-pat"))

	const wantSession = "fresh-session"
	const wantPAT = "fresh-pat"
	cfJWT := validJWT()

	// access token fails (no local cache), access login succeeds.
	binPath := fakeCFBin(t, cfJWT, 0, 1)
	srv := newArgusTestServer(t, cfJWT, wantSession, wantPAT)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	// The freshly obtained PAT must replace the stale one.
	gotPAT, err := keychain.LoadPAT()
	require.NoError(t, err)
	assert.Equal(t, wantPAT, gotPAT)
}

// TestArgusService_Login_CFLoginFails verifies that a cloudflared access login
// failure is surfaced as ErrCFLogin.
func TestArgusService_Login_CFLoginFails(t *testing.T) {
	setupMockKeyring(t)

	// exit 1 on `access login` → ErrCFLogin
	binPath := fakeCFBin(t, "", 1, 1)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("login endpoint should not be called when cf login fails")
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	err := svc.Login(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, auth.ErrCFLogin)
}

// TestArgusService_Login_NoSessionCookie verifies that a login response
// without a session cookie returns ErrNoSessionCookie.
func TestArgusService_Login_NoSessionCookie(t *testing.T) {
	setupMockKeyring(t)

	cfJWT := validJWT()
	binPath := fakeCFBin(t, cfJWT, 0, 0)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Respond 200 but set no session cookie.
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	err := svc.Login(t.Context())
	require.Error(t, err)
	assert.ErrorIs(t, err, auth.ErrNoSessionCookie)
}

// TestArgusService_Login_HappyPath verifies the full flow: cloudflared access
// login is invoked, JWT is parsed from its output, login endpoint returns a
// session cookie, the session is exchanged for a PAT, and the PAT is stored in
// the keychain while the session is discarded.
func TestArgusService_Login_HappyPath(t *testing.T) {
	setupMockKeyring(t)

	const wantSession = "argus-session-xyz"
	const wantPAT = "test-pat-token-abc"
	cfJWT := validJWT()

	// access token fails (no local cache), access login succeeds.
	binPath := fakeCFBin(t, cfJWT, 0, 1)
	srv := newArgusTestServer(t, cfJWT, wantSession, wantPAT)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	// PAT must be stored in the keychain.
	gotPAT, err := keychain.LoadPAT()
	require.NoError(t, err)
	assert.Equal(t, wantPAT, gotPAT)

	// The session should have been deleted after PAT exchange.
	_, sessionErr := keychain.Load()
	assert.Error(t, sessionErr, "session should be deleted after PAT is stored")
}

// TestArgusService_Login_UsesCachedCFToken verifies that when a valid CF token
// is already available from `cloudflared access token`, the full `access login`
// browser flow is NOT invoked and the cached token is used directly to obtain
// a PAT.
func TestArgusService_Login_UsesCachedCFToken(t *testing.T) {
	setupMockKeyring(t)

	cfJWT := validJWT()

	const wantSession = "argus-session-from-cache"
	const wantPAT = "pat-from-cached-cf"

	// access token succeeds (returns cached JWT), access login would fail.
	binPath := fakeCFBin(t, cfJWT, 1, 0)

	srv := newArgusTestServer(t, cfJWT, wantSession, wantPAT)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	// PAT must be stored; session should be gone.
	gotPAT, err := keychain.LoadPAT()
	require.NoError(t, err)
	assert.Equal(t, wantPAT, gotPAT)

	_, sessionErr := keychain.Load()
	assert.Error(t, sessionErr, "session should be deleted after PAT is stored")
}

// TestArgusService_Login_ExpiredCFToken verifies that when `cloudflared access
// token` returns an expired CF token, the CLI falls through to
// `cloudflared access login` to obtain a fresh one, then exchanges it for a PAT.
func TestArgusService_Login_ExpiredCFToken(t *testing.T) {
	setupMockKeyring(t)

	expiredCFJWT := expiredJWT()
	freshCFJWT := validJWT()

	// We need a binary where `access token` returns the expired token and
	// `access login` returns the fresh one. Build a custom binary for this.
	binPath := fakeCFBinDualToken(t, expiredCFJWT, freshCFJWT)

	const wantSession = "argus-session-after-refresh"
	const wantPAT = "pat-after-refresh"

	srv := newArgusTestServer(t, freshCFJWT, wantSession, wantPAT)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	// PAT must be stored; session should be gone.
	gotPAT, err := keychain.LoadPAT()
	require.NoError(t, err)
	assert.Equal(t, wantPAT, gotPAT)

	_, sessionErr := keychain.Load()
	assert.Error(t, sessionErr, "session should be deleted after PAT is stored")
}

// --------------------------------------------------------------------------
// lastNonEmptyLine edge cases
// --------------------------------------------------------------------------

func TestLastNonEmptyLine_EmptyString(t *testing.T) {
	t.Parallel()

	assert.Equal(t, "", auth.LastNonEmptyLine(""),
		"empty string should return empty string")
}

func TestLastNonEmptyLine_AllWhitespace(t *testing.T) {
	t.Parallel()

	assert.Equal(t, "", auth.LastNonEmptyLine("   \n\t\n  \n"),
		"all-whitespace string should return empty string")
}

func TestLastNonEmptyLine_SingleLine(t *testing.T) {
	t.Parallel()

	assert.Equal(t, "hello", auth.LastNonEmptyLine("hello"),
		"single non-empty line should be returned")
}

func TestLastNonEmptyLine_NoTrailingNewline(t *testing.T) {
	t.Parallel()

	// "line1\nline2" — last line is "line2" with no trailing newline.
	assert.Equal(t, "line2", auth.LastNonEmptyLine("line1\nline2"))
}

func TestLastNonEmptyLine_TrailingNewlines(t *testing.T) {
	t.Parallel()

	// The function should skip trailing empty lines.
	assert.Equal(t, "last", auth.LastNonEmptyLine("first\nlast\n\n\n"))
}

func TestLastNonEmptyLine_MultipleLines(t *testing.T) {
	t.Parallel()

	input := "line one\nline two\nline three"
	assert.Equal(t, "line three", auth.LastNonEmptyLine(input))
}

// --------------------------------------------------------------------------
// ErrStartingProcess — binary path does not exist
// --------------------------------------------------------------------------

func TestArgusService_Login_ErrStartingProcess(t *testing.T) {
	setupMockKeyring(t)

	// Use a path that does not exist as the cloudflared binary.
	nonExistentBin := filepath.Join(t.TempDir(), "does-not-exist")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("login endpoint should not be called when binary does not exist")
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, nonExistentBin,
		auth.WithHTTPClient(srv.Client()),
	)

	err := svc.Login(t.Context())
	require.Error(t, err)
	// The underlying exec error wraps ErrCFLogin (exec.Command fails with
	// "no such file or directory" which surfaces through runCFLogin).
	assert.ErrorIs(t, err, auth.ErrCFLogin)
}
