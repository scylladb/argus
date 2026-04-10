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
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/jwt"
	"github.com/scylladb/argus/cli/internal/keychain"
	"github.com/scylladb/argus/cli/internal/models"
)

const (
	// cfTokenMaxAge is the maximum time a Cloudflare Access JWT is considered
	// fresh after it was issued. Tokens older than this trigger a new
	// `cloudflared access login` even if the token's own "exp" claim has not
	// yet been reached.
	cfTokenMaxAge = 12 * time.Hour
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

	// ErrFetchingToken is returned when the GET /api/v1/user/token call fails.
	ErrFetchingToken = errors.New("auth: fetching API token from server")

	// ErrStoringPAT is returned when the PAT cannot be persisted in the
	// system keychain after successful token exchange.
	ErrStoringPAT = errors.New("auth: storing API token in keychain")
)

// ArgusService handles the Argus-side of authentication: it fetches a
// Cloudflare Access token via the cloudflared binary, exchanges it for an
// Argus session token, immediately exchanges that session for a durable
// Argus API token (PAT), and persists the PAT in the system keychain.
//
// Using a PAT rather than a session cookie as the long-lived credential is
// more robust: sessions have short server-side TTLs and are tied to CF,
// whereas PATs survive CF token expiry and work in CI without a browser.
//
// The full flow on a cache miss is:
//  1. Run `cloudflared access login --no-verbose --auto-close --app <url> <url>`.
//     This opens a browser window, authenticates the user, and writes the token
//     file to ~/.cloudflared/.  The JWT is the last non-empty line of stdout.
//  2. Cache the JWT in the OS keychain for future invocations.
//  3. Exchange the JWT for an Argus session cookie via POST /auth/login/cf.
//  4. Use that session to call GET /api/v1/user/token, obtaining (or generating)
//     the caller's Argus API token.
//  5. Store the API token as the primary credential under the "pat" keychain key
//     and discard the session cookie — the PAT is the durable credential.
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

// CachedCFToken reads the Cloudflare Access JWT from cloudflared's local
// token cache (~/.cloudflared/) without any network call or browser
// interaction.  It returns a non-expired, non-stale token on success, or an
// error if the cached token is missing, expired, or older than [cfTokenMaxAge].
//
// This is intended for attaching the CF Access cookie to normal API requests
// so they pass through Cloudflare Access to the backend.
func (s *ArgusService) CachedCFToken(ctx context.Context) (string, error) {
	cached, err := s.runCFAccessToken(ctx)
	if err != nil {
		return "", err
	}
	expired, jwtErr := jwt.IsExpired(cached)
	if jwtErr != nil {
		return "", jwtErr
	}
	if expired {
		return "", fmt.Errorf("%w: cached CF token is expired", ErrGettingCFToken)
	}
	tooOld, ageErr := jwt.IsOlderThan(cached, cfTokenMaxAge)
	if ageErr != nil {
		return "", ageErr
	}
	if tooOld {
		return "", fmt.Errorf("%w: cached CF token is older than %s", ErrGettingCFToken, cfTokenMaxAge)
	}
	return cached, nil
}

// Login obtains a Cloudflare Access token, exchanges it for an Argus session,
// immediately trades that session for a durable Argus API token (PAT) via
// GET /api/v1/user/token, and stores the PAT in the system keychain.
//
// Login always performs the full cloudflared authentication flow.  Callers
// that want to avoid unnecessary logins should verify their existing
// credentials first (e.g. by making a lightweight API call) and only call
// Login when those credentials are known to be invalid.
func (s *ArgusService) Login(ctx context.Context) error {
	cfToken, err := s.GetOrFetchCFToken(ctx)
	if err != nil {
		return err
	}

	session, err := s.login(ctx, cfToken)
	if err != nil {
		return err
	}

	// Exchange the short-lived session for a durable PAT.
	// The CF token must accompany the session cookie so the request passes
	// through Cloudflare Access to reach the Argus backend.
	pat, err := s.fetchPAT(ctx, session, cfToken)
	if err != nil {
		// Fetching the PAT failed. Fall back to persisting the session so the
		// user is at least authenticated for this invocation, but warn them.
		_ = keychain.Store(session)
		return fmt.Errorf("%w (falling back to session cookie): %w", ErrFetchingToken, err)
	}

	if err := keychain.StorePAT(pat); err != nil {
		return errors.Join(ErrStoringPAT, err)
	}

	// The PAT supersedes the session — drop it from the keychain so we never
	// accidentally send a stale session cookie alongside the PAT.
	_ = keychain.Delete()

	return nil
}

// fetchPAT calls GET /api/v1/user/token authenticated with the given session
// cookie and CF Access JWT, and returns the Argus API token string.
//
// Both the session cookie and the CF token are required: the session
// authenticates against Argus itself while the CF token passes through the
// Cloudflare Access layer that sits in front of the service.
func (s *ArgusService) fetchPAT(ctx context.Context, session, cfToken string) (string, error) {
	opts := make([]api.ClientOption, 0, 2+len(s.clientOpts))
	opts = append(opts, api.WithSession(session))
	opts = append(opts, api.WithCFToken(cfToken))
	opts = append(opts, s.clientOpts...)

	client, err := api.New(s.argusURL, opts...)
	if err != nil {
		return "", fmt.Errorf("%w: building client: %w", ErrFetchingToken, err)
	}

	req, err := client.NewRequest(ctx, http.MethodGet, api.UserToken, nil)
	if err != nil {
		return "", fmt.Errorf("%w: building request: %w", ErrFetchingToken, err)
	}

	result, err := api.DoJSON[models.UserTokenResponse](client, req)
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrFetchingToken, err)
	}

	if result.Token == "" {
		return "", fmt.Errorf("%w: server returned an empty token", ErrFetchingToken)
	}

	return result.Token, nil
}

// GetOrFetchCFToken returns a valid CF Access JWT.  It first tries
// `cloudflared access token --app <url>` which reads the token from
// cloudflared's local token cache (~/.cloudflared/) without any network call
// or browser interaction.  If that fails or the token is expired / too old,
// it falls back to `cloudflared access login` which opens a browser.
func (s *ArgusService) GetOrFetchCFToken(ctx context.Context) (string, error) {
	// Try the fast, local-only `access token` subcommand first.
	if cached, err := s.runCFAccessToken(ctx); err == nil {
		expired, jwtErr := jwt.IsExpired(cached)
		if jwtErr == nil && !expired {
			// Also enforce a hard 12 h maximum regardless of what the token's
			// own "exp" claim says — CF tokens can be issued with long
			// lifetimes but we want to re-authenticate regularly.
			tooOld, ageErr := jwt.IsOlderThan(cached, cfTokenMaxAge)
			if ageErr == nil && !tooOld {
				return cached, nil
			}
		}
	}

	// Fall back to the full browser-based login flow.
	fresh, err := s.runCFLogin(ctx)
	if err != nil {
		return "", err
	}

	return fresh, nil
}

// runCFAccessToken runs:
//
//	cloudflared access token --app <argusURL>
//
// This reads the CF Access JWT from cloudflared's local token cache
// (~/.cloudflared/) without any network call or browser interaction.
// It returns the token string on success.
func (s *ArgusService) runCFAccessToken(ctx context.Context) (string, error) {
	cmd := exec.CommandContext(ctx, s.cloudflaredBin, //nolint:gosec
		"access", "token",
		"--app", s.argusURL,
	)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = io.Discard // suppress progress/error output

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("%w: %w", ErrGettingCFToken, err)
	}

	token := lastNonEmptyLine(out.String())
	if token == "" {
		return "", fmt.Errorf("%w: no token in cloudflared output", ErrGettingCFToken)
	}

	return token, nil
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
	// Capture stdout entirely; we will selectively print browser-URL lines
	// and suppress the JWT token line so it does not appear on the terminal.
	cmd.Stdout = &out
	// Stderr carries progress / error messages and goes directly to the
	// terminal without capturing — no sensitive data appears there.
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("%w: %w", ErrCFLogin, err)
	}

	if err := cmd.Wait(); err != nil {
		return "", fmt.Errorf("%w: %w\n%s", ErrCFLogin, err, out.String())
	}

	// The JWT is the last non-empty line of stdout.  Print all lines except
	// the token itself so the user sees the browser-URL prompt.
	token := lastNonEmptyLine(out.String())
	if token == "" {
		return "", fmt.Errorf("%w: no token found in cloudflared output:\n%s", ErrCFLogin, out.String())
	}
	printCFLoginOutput(out.String(), token)

	return token, nil
}

// printCFLoginOutput writes every non-empty line from cloudflared stdout to
// os.Stdout, skipping the JWT token line so it is never displayed to the user.
func printCFLoginOutput(output, token string) {
	for _, line := range strings.Split(output, "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		if strings.TrimSpace(line) == token {
			// Skip the JWT — it is a secret and should not appear on the terminal.
			continue
		}
		_, _ = fmt.Fprintln(os.Stdout, line)
	}
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
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

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
