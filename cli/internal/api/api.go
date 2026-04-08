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
	"time"

	"github.com/scylladb/argus/cli/internal/models"
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

	// ErrAPIError is returned (wrapped inside an [APIError]) when the backend
	// returns a response with status "error".
	ErrAPIError = errors.New("api: server returned error")

	// ErrUnauthorized is returned (wrapped) by [DoJSON] when the server
	// responds with a non-JSON content type on a 2xx status, which almost
	// always means a Cloudflare Access authentication challenge was served
	// instead of the expected API response.
	ErrUnauthorized = errors.New("unauthorized")
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

	// cfAccessClientId is part one of the cf login jwt override (service level)
	cfAccessClientId string
	// cfAccessClientSecret is part two of the cf login jwt override (service level)
	cfAccessClientSecret string
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

// WithHTTPClient replaces the underlying [http.Client]. Useful in tests.
func WithHTTPClient(hc *http.Client) ClientOption {
	return func(c *Client) { c.httpClient = hc }
}

// WithCFAccessSecret attaches ID and Secret for CF Access
func WithCFAccessSecret(id string, secret string) ClientOption {
	return func(c *Client) { c.cfAccessClientId = id; c.cfAccessClientSecret = secret }
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

// attachAuth adds the session cookie, CF_Authorization cookie, and/or API
// token header to req.
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
	if c.cfAccessClientId != "" {
		req.Header.Set("CF-Access-Client-Id", c.cfAccessClientId)
	}
	if c.cfAccessClientSecret != "" {
		req.Header.Set("CF-Access-Client-Secret", c.cfAccessClientSecret)
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

// DoStream executes req using a client with no timeout, suitable for streaming
// large responses such as log file downloads. The caller is responsible for
// closing the response body.
func (c *Client) DoStream(req *http.Request) (*http.Response, error) {
	if req.URL.Host == "" {
		resolved := c.baseURL.ResolveReference(req.URL)
		req.URL = resolved
	}

	streamClient := &http.Client{
		Transport:     c.httpClient.Transport,
		CheckRedirect: c.httpClient.CheckRedirect,
		Jar:           c.httpClient.Jar,
		// No Timeout: large downloads must not be cut off by the default 30 s limit.
	}
	return streamClient.Do(req)
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
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return zero, fmt.Errorf("server returned %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}

	if contentType := resp.Header.Get("Content-Type"); contentType != "application/json" {
		// Non-JSON response from a non-error status code is almost always a
		// Cloudflare or reverse-proxy authentication challenge (HTML login
		// page). Treat it as an authorization failure with an actionable
		// message so LLM consumers and humans can self-correct by
		// re-authenticating rather than seeing a confusing decode error.
		return zero, fmt.Errorf(
			"%w: server returned Content-Type %q instead of application/json — "+
				"this usually means authentication failed or the session expired; "+
				"re-authenticate with `argus auth` or set the ARGUS_TOKEN environment variable",
			ErrUnauthorized,
			contentType,
		)
	}

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return zero, fmt.Errorf("%w: %w", ErrReadingBody, err)
	}

	var envelope models.APIResponse[T]
	if err := json.Unmarshal(raw, &envelope); err != nil {
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
