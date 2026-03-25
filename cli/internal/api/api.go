package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/scylladb/argus/cli/internal/models"
)

const (
	// maxResponseSize is the maximum number of bytes read from an HTTP response
	// body. This prevents a misbehaving or malicious server from exhausting
	// memory.
	maxResponseSize = 10 << 20 // 10 MB
)

const (
	defaultTimeout = 30 * time.Second
)

// Sentinel errors returned by the api package.
var (
	// ErrInvalidBaseURL is returned when the base URL supplied to [New] cannot
	// be parsed as a valid absolute URL.
	ErrInvalidBaseURL = errors.New("api: invalid base URL")

	// ErrInvalidPath is returned when a path supplied to [Client.NewRequest]
	// cannot be parsed as a URL reference.
	ErrInvalidPath = errors.New("api: invalid path")

	// ErrBuildingRequest is returned when [http.NewRequestWithContext] fails
	// inside [Client.NewRequest].
	ErrBuildingRequest = errors.New("api: building request")

	// ErrEncodingBody is returned when JSON-encoding the request body fails.
	ErrEncodingBody = errors.New("api: encoding request body")

	// ErrReadingBody is returned when reading the HTTP response body fails.
	ErrReadingBody = errors.New("api: reading response body")

	// ErrDecodingResponse is returned when the HTTP response cannot be decoded
	// as a valid [models.APIResponse] envelope.
	ErrDecodingResponse = errors.New("api: decoding response")

	// ErrUnexpectedStatus is returned when the server responds with a
	// non-2xx status code and the body is not a valid API error envelope.
	ErrUnexpectedStatus = errors.New("api: unexpected HTTP status")

	// ErrAPIError is returned (wrapped inside an [APIError]) when the backend
	// returns a response with status "error".
	ErrAPIError = errors.New("api: server returned error")

	// ErrAuthRequired is returned when the server responds with HTML instead
	// of JSON, which typically indicates a Cloudflare Access login page.
	// The user should re-authenticate with `argus auth --force`.
	ErrAuthRequired = errors.New("api: authentication required (got HTML instead of JSON — run `argus auth --force` to re-authenticate)")
)

// APIError wraps a backend error response so callers can inspect the details
// via errors.As while still getting ErrAPIError from errors.Is.
type APIError struct {
	Body models.ErrorBody
}

func (e *APIError) Error() string {
	return fmt.Sprintf("%s: %s (exception: %s)", ErrAPIError, e.Body.Message, e.Body.Exception)
}

func (e *APIError) Unwrap() error { return ErrAPIError }

// Client is an HTTP client scoped to a single Argus base URL.
type Client struct {
	baseURL    *url.URL
	httpClient *http.Client

	// session is the value of the "session" cookie, if any.
	session string
	// cfToken is the Cloudflare Access JWT sent as the "CF_Authorization"
	// cookie, used only during the /auth/login/cf handshake.
	cfToken string
	// apiToken is used as "Authorization: token <apiToken>" header, if any.
	apiToken string
	// cfAccessClientID is sent as "CF-Access-Client-Id" header for
	// Cloudflare Access service-token auth.
	cfAccessClientID string
	// cfAccessClientSecret is sent as "CF-Access-Client-Secret" header.
	cfAccessClientSecret string
	// extraHeaders are arbitrary headers added to every request.
	extraHeaders map[string]string
}

// ClientOption is a functional option for [New].
type ClientOption func(*Client)

// WithSession attaches a session cookie to every request made by the client.
// The value is the raw cookie value obtained from the system keychain after
// a successful [ArgusService.Login].
func WithSession(session string) ClientOption {
	return func(c *Client) { c.session = session }
}

// WithCFToken attaches a Cloudflare Access JWT as the "CF_Authorization"
// cookie on every request made by the client. This is only needed when
// constructing a short-lived client for the /auth/login/cf handshake.
func WithCFToken(token string) ClientOption {
	return func(c *Client) { c.cfToken = token }
}

// WithAPIToken attaches an API token to every request as the
// "Authorization: token <apiToken>" header.
func WithAPIToken(token string) ClientOption {
	return func(c *Client) { c.apiToken = token }
}

// WithCFAccessHeaders attaches Cloudflare Access service-token headers
// (CF-Access-Client-Id and CF-Access-Client-Secret) to every request.
func WithCFAccessHeaders(clientID, clientSecret string) ClientOption {
	return func(c *Client) {
		c.cfAccessClientID = clientID
		c.cfAccessClientSecret = clientSecret
	}
}

// WithExtraHeaders attaches arbitrary headers to every request.
func WithExtraHeaders(headers map[string]string) ClientOption {
	return func(c *Client) { c.extraHeaders = headers }
}

// WithHTTPClient replaces the underlying [http.Client]. Useful in tests.
func WithHTTPClient(hc *http.Client) ClientOption {
	return func(c *Client) { c.httpClient = hc }
}

// New constructs a Client targeting rawBaseURL.
// rawBaseURL must be a valid absolute URL (e.g. "https://argus.scylladb.com").
func New(rawBaseURL string, opts ...ClientOption) (*Client, error) {
	u, err := url.ParseRequestURI(rawBaseURL)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrInvalidBaseURL, rawBaseURL, err)
	}

	c := &Client{
		baseURL: u,
		httpClient: &http.Client{
			Timeout: defaultTimeout,
		},
	}

	for _, o := range opts {
		o(c)
	}

	return c, nil
}

// BaseURL returns the base URL the client is configured with.
func (c *Client) BaseURL() string {
	return c.baseURL.String()
}

// NewRequest constructs an [http.Request] for the given method and path.
// If body is non-nil it is JSON-encoded and the Content-Type header is set to
// "application/json". The configured session cookie and/or API token are
// attached automatically.
func (c *Client) NewRequest(ctx context.Context, method, path string, body any) (*http.Request, error) {
	rel, err := url.Parse(path)
	if err != nil {
		return nil, fmt.Errorf("%w %q: %w", ErrInvalidPath, path, err)
	}

	target := c.baseURL.ResolveReference(rel)

	var bodyReader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("%w: %w", ErrEncodingBody, err)
		}
		bodyReader = bytes.NewReader(b)
	}

	req, err := http.NewRequestWithContext(ctx, method, target.String(), bodyReader)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrBuildingRequest, err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	c.attachAuth(req)

	return req, nil
}

// attachAuth adds the session cookie, CF_Authorization cookie, API token
// header, CF Access service-token headers, and extra headers to req.
func (c *Client) attachAuth(req *http.Request) {
	if c.session != "" {
		req.AddCookie(&http.Cookie{Name: "session", Value: c.session})
	}
	if c.cfToken != "" {
		req.AddCookie(&http.Cookie{Name: "CF_Authorization", Value: c.cfToken})
	}
	if c.apiToken != "" {
		req.Header.Set("Authorization", "token "+c.apiToken)
	}
	if c.cfAccessClientID != "" {
		req.Header.Set("CF-Access-Client-Id", c.cfAccessClientID)
	}
	if c.cfAccessClientSecret != "" {
		req.Header.Set("CF-Access-Client-Secret", c.cfAccessClientSecret)
	}
	for k, v := range c.extraHeaders {
		req.Header.Set(k, v)
	}
}

// Do executes req and returns the raw [http.Response].
// The caller is responsible for closing the response body.
func (c *Client) Do(req *http.Request) (*http.Response, error) {
	if req.URL.Host == "" {
		resolved := c.baseURL.ResolveReference(req.URL)
		req.URL = resolved
	}

	return c.httpClient.Do(req)
}

// isHTMLResponse returns true when the response body looks like HTML rather
// than JSON. This typically happens when Cloudflare Access intercepts the
// request and returns a login page.
func isHTMLResponse(body []byte, header http.Header) bool {
	ct := header.Get("Content-Type")
	if strings.Contains(ct, "text/html") {
		return true
	}
	trimmed := bytes.TrimLeft(body, " \t\r\n")
	return len(trimmed) > 0 && trimmed[0] == '<'
}

// DoJSON executes req, reads the response body, and decodes it as an
// [models.APIResponse] envelope. It returns the decoded payload T on success
// or an [*APIError] (wrapping [ErrAPIError]) when the backend signals an error
// in the envelope.
//
// This is a package-level generic function rather than a method because Go
// does not support generic methods with additional type parameters.
func DoJSON[T any](c *Client, req *http.Request) (T, error) {
	var zero T

	resp, err := c.Do(req)
	if err != nil {
		return zero, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseSize))
	if err != nil {
		return zero, fmt.Errorf("%w: %w", ErrReadingBody, err)
	}

	// Detect HTML responses (e.g. Cloudflare Access login page) before
	// attempting JSON parsing.
	if isHTMLResponse(raw, resp.Header) {
		return zero, ErrAuthRequired
	}

	var envelope models.APIResponse[T]
	if err := json.Unmarshal(raw, &envelope); err != nil {
		// If the status code indicates an error and the body isn't valid JSON
		// (e.g. an HTML error page), return a clear status-based error.
		if resp.StatusCode >= 400 {
			return zero, fmt.Errorf("%w: %d %s", ErrUnexpectedStatus, resp.StatusCode, http.StatusText(resp.StatusCode))
		}
		return zero, fmt.Errorf("%w: %w", ErrDecodingResponse, err)
	}

	if envelope.IsError() {
		body, err := envelope.DecodeError()
		if err != nil {
			return zero, fmt.Errorf("%w: %w", ErrDecodingResponse, err)
		}
		return zero, &APIError{Body: body}
	}

	result, err := envelope.Decode()
	if err != nil {
		return zero, fmt.Errorf("%w: %w", ErrDecodingResponse, err)
	}

	return result, nil
}

// DoRedirect performs a request that may return a redirect. It returns the
// Location header if the server issues a 3xx redirect, or parses the Argus
// envelope for a URL string on a 200 response.
func DoRedirect(c *Client, ctx context.Context, method, path string) (string, error) {
	req, err := c.NewRequest(ctx, method, path, nil)
	if err != nil {
		return "", err
	}

	// Use a client that does not follow redirects.
	noRedirectClient := *c.httpClient
	noRedirectClient.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}

	resp, err := noRedirectClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if loc := resp.Header.Get("Location"); loc != "" {
		return loc, nil
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseSize))
	if err != nil {
		return "", fmt.Errorf("%w: %w", ErrReadingBody, err)
	}

	if resp.StatusCode == http.StatusOK {
		var envelope struct {
			Status   string `json:"status"`
			Response string `json:"response"`
		}
		if json.Unmarshal(raw, &envelope) == nil && envelope.Response != "" {
			return envelope.Response, nil
		}
	}

	return "", fmt.Errorf("%w: %d %s", ErrUnexpectedStatus, resp.StatusCode, http.StatusText(resp.StatusCode))
}

// DownloadFile downloads a file from url (no auth headers — typically a
// pre-signed S3 URL) and saves it to dst using an atomic temp-file + rename.
func DownloadFile(url, dst string) (int64, error) {
	resp, err := http.Get(url) //nolint:gosec // pre-signed URL from Argus API
	if err != nil {
		return 0, fmt.Errorf("downloading file: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("download failed: HTTP %d", resp.StatusCode)
	}

	tmp := dst + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return 0, fmt.Errorf("creating file: %w", err)
	}

	n, err := io.Copy(f, resp.Body)
	f.Close()
	if err != nil {
		os.Remove(tmp)
		return 0, fmt.Errorf("writing file: %w", err)
	}
	if err := os.Rename(tmp, dst); err != nil {
		os.Remove(tmp)
		return 0, fmt.Errorf("renaming file: %w", err)
	}
	return n, nil
}
