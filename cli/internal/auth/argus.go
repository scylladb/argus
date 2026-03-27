package auth

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/jwt"
	"github.com/scylladb/argus/cli/internal/keychain"
)

// Sentinel errors for the Argus authentication step.
var (
	// ErrGettingCFToken is returned when the cloudflared access token
	// sub-command fails.
	ErrGettingCFToken = errors.New("auth: getting cloudflare access token")

	// ErrCFLogin is returned when the cloudflared access login sub-command
	// fails or produces no recognisable JWT in its output.
	ErrCFLogin = errors.New("auth: cloudflared access login failed")

	// ErrLoginRequest is returned when the HTTP call to /auth/login/cf fails
	// at the transport level.
	ErrLoginRequest = errors.New("auth: login request failed")

	// ErrNoSessionCookie is returned when the Argus login endpoint responds
	// without a session cookie, indicating an unexpected server response.
	ErrNoSessionCookie = errors.New("auth: no session cookie in login response")

	// ErrStoringSession is returned when the session token cannot be persisted
	// in the system keychain.
	ErrStoringSession = errors.New("auth: storing session token")
)

// ArgusService handles the Argus-side of authentication: it fetches a
// Cloudflare Access token via the cloudflared binary, exchanges it for an
// Argus session token, and persists both tokens in the system keychain.
//
// On subsequent invocations the CF Access JWT is loaded from the keychain and
// reused as long as it has not expired, which means cloudflared does not need
// to be invoked again.
//
// The full flow on a cache miss is:
//  1. Run `cloudflared access login --no-verbose --auto-close --app <url> <url>`.
//     This opens a browser window, authenticates the user, and writes the token
//     file to ~/.cloudflared/.  The JWT is the last non-empty line of stdout.
//  2. Cache the JWT in the OS keychain for future invocations.
//  3. Exchange the JWT for an Argus session cookie via POST /auth/login/cf.
type ArgusService struct {
	// argusURL is the base URL of the Argus instance (e.g. https://argus.example.com).
	argusURL string

	// cloudflaredBin is the path to the cloudflared executable used to obtain
	// the CF Access JWT.
	cloudflaredBin string

	// clientOpts are forwarded to api.New when building the short-lived client
	// used for the /auth/login/cf request. Primarily useful in tests.
	clientOpts []api.ClientOption
}

// ArgusOption is a functional option for [NewArgusService].
type ArgusOption func(*ArgusService)

// WithHTTPClient overrides the HTTP client used for the login request.
// Primarily useful in tests.
func WithHTTPClient(c *http.Client) ArgusOption {
	return func(s *ArgusService) {
		s.clientOpts = append(s.clientOpts, api.WithHTTPClient(c))
	}
}

// NewArgusService constructs an ArgusService for the given Argus base URL.
// cloudflaredBin must be the resolved path to the cloudflared executable
// (as returned by CloudflaredService.Ensure).
func NewArgusService(argusURL, cloudflaredBin string, opts ...ArgusOption) *ArgusService {
	s := &ArgusService{
		argusURL:       argusURL,
		cloudflaredBin: cloudflaredBin,
	}

	for _, o := range opts {
		o(s)
	}

	return s
}

// HasValidCFToken reports whether a non-expired Cloudflare Access JWT is
// currently stored in the keychain.  It is intended to be called by the
// command layer so it can decide whether the CF tunnel step is still required.
func HasValidCFToken() bool {
	tok, err := keychain.LoadCFToken()
	if err != nil {
		return false
	}
	expired, err := jwt.IsExpired(tok)
	if err != nil {
		// Malformed token in keychain — treat as absent.
		_ = keychain.DeleteCFToken()
		return false
	}
	if expired {
		_ = keychain.DeleteCFToken()
		return false
	}
	return true
}

// Login obtains a Cloudflare Access token, exchanges it for an Argus session
// token, and stores both tokens in the system keychain.
//
// Short-circuit order:
//  1. If a valid Argus session already exists → return immediately.
//  2. If a valid (non-expired) CF token is cached in the keychain → reuse it,
//     skipping cloudflared entirely.
//  3. Otherwise run `cloudflared access login` to open the browser auth flow,
//     parse the JWT from its output, and store it for future use.
func (s *ArgusService) Login(ctx context.Context) error {
	// Fast path: a valid Argus token is already cached.
	if _, err := keychain.LoadPAT(); err == nil {
		return nil
	}

	// Fast path: a valid Argus session is already cached.
	if _, err := keychain.Load(); err == nil {
		return nil
	}

	cfToken, err := s.getOrFetchCFToken(ctx)
	if err != nil {
		return err
	}

	session, err := s.login(ctx, cfToken)
	if err != nil {
		return err
	}

	if err := keychain.Store(session); err != nil {
		return errors.Join(ErrStoringSession, err)
	}

	return nil
}

// getOrFetchCFToken returns a valid CF Access JWT. It first checks the
// keychain; if a non-expired token is found it is returned immediately.
// Otherwise `cloudflared access login` is invoked to perform the browser auth
// flow, the resulting token is stored in the keychain for future use, and it
// is returned.
func (s *ArgusService) getOrFetchCFToken(ctx context.Context) (string, error) {
	// Try the keychain first.
	if cached, err := keychain.LoadCFToken(); err == nil {
		expired, jwtErr := jwt.IsExpired(cached)
		if jwtErr == nil && !expired {
			return cached, nil
		}
		// Token is expired or malformed — purge it so we fetch a fresh one.
		_ = keychain.DeleteCFToken()
	}

	// Fall back to the full browser-based login flow.
	fresh, err := s.runCFLogin(ctx)
	if err != nil {
		return "", err
	}

	// Best-effort: store the fresh token so the next invocation can skip
	// cloudflared.  A failure here is non-fatal — we still have the token.
	_ = keychain.StoreCFToken(fresh)

	return fresh, nil
}

// runCFLogin shells out to:
//
//	cloudflared access login --no-verbose --auto-close --app <argusURL> <argusURL>
//
// cloudflared opens a browser window for the user to authenticate.  Upon
// success it prints a URL (for manual use) followed by the JWT on the last
// non-empty line of stdout.  This function captures that output and returns
// the JWT.
func (s *ArgusService) runCFLogin(ctx context.Context) (string, error) {
	cmd := exec.CommandContext(ctx, s.cloudflaredBin, //nolint:gosec
		"access", "login",
		"--no-verbose",
		"--auto-close",
		"--app", s.argusURL,
		s.argusURL,
	)
	var out bytes.Buffer
	cmd.Stdout = io.MultiWriter(os.Stdout, &out)
	cmd.Stderr = io.MultiWriter(os.Stderr, &out)

	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("%w: %w", ErrCFLogin, err)
	}

	if err := cmd.Wait(); err != nil {
		return "", fmt.Errorf("%w: %w\n%s", ErrCFLogin, err, out.String())
	}

	// The JWT is the last non-empty line of the output.
	token := lastNonEmptyLine(out.String())
	if token == "" {
		return "", fmt.Errorf("%w: no token found in cloudflared output:\n%s", ErrCFLogin, out.String())
	}

	return token, nil
}

// getCFToken shells out to `cloudflared access token --app=<argusURL>` to
// read a previously cached Cloudflare Access JWT from ~/.cloudflared/.
// This is the fast path used when cloudflared already stored a token on disk
// but our keychain cache is empty (e.g. first run on a new machine after
// cloudflared login was already done separately).
func (s *ArgusService) getCFToken(ctx context.Context) (string, error) {
	out, err := exec.CommandContext(ctx, s.cloudflaredBin, //nolint:gosec
		"access", "token", "--no-verbose", fmt.Sprintf("-app=%s", s.argusURL),
	).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%w: %w\n%s", ErrGettingCFToken, err, out)
	}
	return strings.TrimSpace(string(out)), nil
}

// login POSTs to /auth/login/cf with the CF token attached via api.Client and
// returns the session cookie value from the response.
func (s *ArgusService) login(ctx context.Context, cfToken string) (string, error) {
	// Build a short-lived client. Option precedence (left-to-right, last wins):
	//   1. no-redirect transport (default safe behaviour)
	//   2. CF token cookie
	//   3. caller-supplied overrides (e.g. test http.Client replaces the default)
	noRedirect := &http.Client{
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	opts := make([]api.ClientOption, 0, 2+len(s.clientOpts))
	opts = append(opts, api.WithHTTPClient(noRedirect))
	opts = append(opts, api.WithCFToken(cfToken))
	opts = append(opts, s.clientOpts...)

	client, err := api.New(s.argusURL, opts...)
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrLoginRequest, err)
	}

	req, err := client.NewRequest(ctx, http.MethodPost, "/auth/login/cf", nil)
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrLoginRequest, err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrLoginRequest, err)
	}
	defer resp.Body.Close()

	for _, c := range resp.Cookies() {
		if c.Name == "session" {
			return c.Value, nil
		}
	}

	return "", fmt.Errorf("%w (HTTP %d)", ErrNoSessionCookie, resp.StatusCode)
}

// lastNonEmptyLine returns the last non-whitespace-only line in s.
func lastNonEmptyLine(s string) string {
	lines := strings.Split(s, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if t := strings.TrimSpace(lines[i]); t != "" {
			return t
		}
	}
	return ""
}
