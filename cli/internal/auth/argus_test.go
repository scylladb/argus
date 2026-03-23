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

// makeJWT builds a minimal unsigned JWT with the given exp Unix timestamp.
// The header and signature are stubs — only the payload matters for our tests.
func makeJWT(exp int64) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))

	type payload struct {
		Sub string `json:"sub"`
		Exp int64  `json:"exp"`
	}
	raw, _ := json.Marshal(payload{Sub: "testuser", Exp: exp})
	payloadB64 := base64.RawURLEncoding.EncodeToString(raw)

	return fmt.Sprintf("%s.%s.stub-signature", header, payloadB64)
}

// validJWT returns a JWT with an expiry one hour in the future.
func validJWT() string { return makeJWT(time.Now().Add(time.Hour).Unix()) }

// expiredJWT returns a JWT with an expiry one hour in the past.
func expiredJWT() string { return makeJWT(time.Now().Add(-time.Hour).Unix()) }

// ---- tests -----------------------------------------------------------------

// TestArgusService_Login_AlreadyCached verifies that Login is a no-op when a
// session token is already stored in the keychain.
func TestArgusService_Login_AlreadyCached(t *testing.T) {
	setupMockKeyring(t)
	require.NoError(t, keychain.Store("existing-session"))

	// A server that must never be called.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("login endpoint should not be called when session is cached")
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, "/does-not-matter",
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))
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
// session cookie, and both tokens are stored in the keychain.
func TestArgusService_Login_HappyPath(t *testing.T) {
	setupMockKeyring(t)

	const wantSession = "argus-session-xyz"
	cfJWT := validJWT()

	binPath := fakeCFBin(t, cfJWT, 0, 0)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify the CF_Authorization cookie was sent.
		c, err := r.Cookie("CF_Authorization")
		if err != nil || c.Value != cfJWT {
			http.Error(w, "missing or wrong CF_Authorization cookie", http.StatusBadRequest)
			return
		}
		http.SetCookie(w, &http.Cookie{Name: "session", Value: wantSession})
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	// Argus session must be stored.
	gotSession, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, wantSession, gotSession)

	// CF token must also be stored in the keychain.
	gotCF, err := keychain.LoadCFToken()
	require.NoError(t, err)
	assert.Equal(t, cfJWT, gotCF)
}

// TestArgusService_Login_UsesCachedCFToken verifies that when a valid CF token
// is already in the keychain, cloudflared is NOT invoked and the cached token
// is used directly.
func TestArgusService_Login_UsesCachedCFToken(t *testing.T) {
	setupMockKeyring(t)

	cfJWT := validJWT()
	require.NoError(t, keychain.StoreCFToken(cfJWT))

	const wantSession = "argus-session-from-cache"

	// A cloudflared binary that would fail if called.
	binPath := fakeCFBin(t, "", 1, 1)

	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		c, err := r.Cookie("CF_Authorization")
		if err != nil || c.Value != cfJWT {
			http.Error(w, "wrong CF_Authorization cookie", http.StatusBadRequest)
			return
		}
		http.SetCookie(w, &http.Cookie{Name: "session", Value: wantSession})
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))
	assert.Equal(t, 1, callCount, "login endpoint should be called exactly once")

	gotSession, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, wantSession, gotSession)
}

// TestArgusService_Login_ExpiredCFToken verifies that an expired cached CF
// token is discarded and cloudflared access login is invoked to obtain a fresh
// one.
func TestArgusService_Login_ExpiredCFToken(t *testing.T) {
	setupMockKeyring(t)

	// Plant an expired token in the keychain.
	require.NoError(t, keychain.StoreCFToken(expiredJWT()))

	freshCFJWT := validJWT()
	binPath := fakeCFBin(t, freshCFJWT, 0, 0)

	const wantSession = "argus-session-after-refresh"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := r.Cookie("CF_Authorization")
		if err != nil || c.Value != freshCFJWT {
			http.Error(w, "wrong CF_Authorization cookie", http.StatusBadRequest)
			return
		}
		http.SetCookie(w, &http.Cookie{Name: "session", Value: wantSession})
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	svc := auth.NewArgusService(srv.URL, binPath,
		auth.WithHTTPClient(srv.Client()),
	)
	require.NoError(t, svc.Login(t.Context()))

	gotSession, err := keychain.Load()
	require.NoError(t, err)
	assert.Equal(t, wantSession, gotSession)

	// The fresh CF token must replace the expired one.
	gotCF, err := keychain.LoadCFToken()
	require.NoError(t, err)
	assert.Equal(t, freshCFJWT, gotCF)
}

// TestHasValidCFToken verifies the HasValidCFToken helper covers all branches.
func TestHasValidCFToken_NoCachedToken(t *testing.T) {
	setupMockKeyring(t)
	assert.False(t, auth.HasValidCFToken(), "should be false when no token is stored")
}

func TestHasValidCFToken_ValidToken(t *testing.T) {
	setupMockKeyring(t)
	require.NoError(t, keychain.StoreCFToken(validJWT()))
	assert.True(t, auth.HasValidCFToken(), "should be true when a valid token is stored")
}

func TestHasValidCFToken_ExpiredToken(t *testing.T) {
	setupMockKeyring(t)
	require.NoError(t, keychain.StoreCFToken(expiredJWT()))
	assert.False(t, auth.HasValidCFToken(), "should be false when cached token is expired")

	// The expired token must have been cleaned up.
	_, err := keychain.LoadCFToken()
	assert.ErrorIs(t, err, keychain.ErrCFTokenNotFound)
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
