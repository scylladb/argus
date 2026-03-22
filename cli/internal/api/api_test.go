package api_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------

// okEnvelope wraps payload as {"status":"ok","response":<payload>}.
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

// errEnvelope wraps body as {"status":"error","response":<body>}.
func errEnvelope(t *testing.T, body models.ErrorBody) []byte {
	t.Helper()
	raw, err := json.Marshal(body)
	require.NoError(t, err)
	env := map[string]json.RawMessage{
		"status":   json.RawMessage(`"error"`),
		"response": raw,
	}
	b, err := json.Marshal(env)
	require.NoError(t, err)
	return b
}

// staticHandler returns a handler that always writes body with the given HTTP
// status code.
func staticHandler(code int, body []byte) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(code)
		_, _ = w.Write(body)
	}
}

// --------------------------------------------------------------------------
// New
// --------------------------------------------------------------------------

func TestNew_ValidURL(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)
	require.NotNil(t, c)
	assert.Equal(t, "https://argus.scylladb.com", c.BaseURL())
}

func TestNew_InvalidURL(t *testing.T) {
	_, err := api.New("not a url %%")
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrInvalidBaseURL)
}

func TestNew_RelativeURL(t *testing.T) {
	// url.ParseRequestURI rejects paths without a scheme (no host). Using a
	// plain path-only string that has no scheme should fail.
	_, err := api.New("://no-scheme")
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrInvalidBaseURL)
}

// --------------------------------------------------------------------------
// NewRequest – body encoding
// --------------------------------------------------------------------------

func TestNewRequest_NilBody(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)
	assert.Equal(t, "", req.Header.Get("Content-Type"))
	assert.Nil(t, req.Body)
}

func TestNewRequest_WithBody(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	payload := map[string]string{"key": "value"}
	req, err := c.NewRequest(context.Background(), http.MethodPost, "/api/v1/runs", payload)
	require.NoError(t, err)

	assert.Equal(t, "application/json", req.Header.Get("Content-Type"))
	require.NotNil(t, req.Body)

	raw, err := io.ReadAll(req.Body)
	require.NoError(t, err)

	var got map[string]string
	require.NoError(t, json.Unmarshal(raw, &got))
	assert.Equal(t, payload, got)
}

func TestNewRequest_InvalidPath(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	// A path containing a null byte cannot be parsed by url.Parse.
	_, err = c.NewRequest(context.Background(), http.MethodGet, "/bad\x00path", nil)
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrInvalidPath)
}

// --------------------------------------------------------------------------
// NewRequest – auth attachment
// --------------------------------------------------------------------------

func TestNewRequest_WithSession(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com", api.WithSession("tok123"))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	cookie, err := req.Cookie("session")
	require.NoError(t, err, "session cookie should be present")
	assert.Equal(t, "tok123", cookie.Value)
}

func TestNewRequest_NoSession(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	_, err = req.Cookie("session")
	assert.Error(t, err, "session cookie should be absent")
}

func TestNewRequest_WithAPIToken(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com", api.WithAPIToken("mytoken"))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	assert.Equal(t, "token mytoken", req.Header.Get("Authorization"))
}

func TestNewRequest_NoAPIToken(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	assert.Empty(t, req.Header.Get("Authorization"))
}

func TestNewRequest_BothAuthMethods(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com",
		api.WithSession("sess"),
		api.WithAPIToken("tok"),
	)
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	cookie, err := req.Cookie("session")
	require.NoError(t, err)
	assert.Equal(t, "sess", cookie.Value)
	assert.Equal(t, "token tok", req.Header.Get("Authorization"))
}

func TestNewRequest_WithCFToken(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com", api.WithCFToken("cf-jwt"))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodPost, "/auth/login/cf", nil)
	require.NoError(t, err)

	cookie, err := req.Cookie("CF_Authorization")
	require.NoError(t, err, "CF_Authorization cookie should be present")
	assert.Equal(t, "cf-jwt", cookie.Value)
}

func TestNewRequest_NoCFToken(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com")
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	_, err = req.Cookie("CF_Authorization")
	assert.Error(t, err, "CF_Authorization cookie should be absent")
}

func TestNewRequest_AllAuthOptions(t *testing.T) {
	c, err := api.New("https://argus.scylladb.com",
		api.WithSession("sess"),
		api.WithCFToken("cf-jwt"),
		api.WithAPIToken("tok"),
	)
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodPost, "/auth/login/cf", nil)
	require.NoError(t, err)

	sessCookie, err := req.Cookie("session")
	require.NoError(t, err)
	assert.Equal(t, "sess", sessCookie.Value)

	cfCookie, err := req.Cookie("CF_Authorization")
	require.NoError(t, err)
	assert.Equal(t, "cf-jwt", cfCookie.Value)

	assert.Equal(t, "token tok", req.Header.Get("Authorization"))
}

// --------------------------------------------------------------------------
// DoJSON – success path
// --------------------------------------------------------------------------

type samplePayload struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

func TestDoJSON_Success(t *testing.T) {
	want := samplePayload{ID: "abc", Name: "test-run"}

	srv := httptest.NewServer(staticHandler(http.StatusOK, okEnvelope(t, want)))
	t.Cleanup(srv.Close)

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	got, err := api.DoJSON[samplePayload](c, req)
	require.NoError(t, err)
	assert.Equal(t, want, got)
}

// --------------------------------------------------------------------------
// DoJSON – backend error path
// --------------------------------------------------------------------------

func TestDoJSON_BackendError(t *testing.T) {
	body := models.ErrorBody{
		TraceID:   "trace-001",
		Exception: "SomeException",
		Message:   "something went wrong",
		Arguments: []string{"arg1"},
	}

	srv := httptest.NewServer(staticHandler(http.StatusOK, errEnvelope(t, body)))
	t.Cleanup(srv.Close)

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	_, err = api.DoJSON[samplePayload](c, req)
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrAPIError)

	var apiErr *api.APIError
	require.ErrorAs(t, err, &apiErr)
	assert.Equal(t, body.Message, apiErr.Body.Message)
	assert.Equal(t, body.Exception, apiErr.Body.Exception)
	assert.Equal(t, body.TraceID, apiErr.Body.TraceID)
}

// --------------------------------------------------------------------------
// DoJSON – malformed JSON
// --------------------------------------------------------------------------

func TestDoJSON_MalformedJSON(t *testing.T) {
	srv := httptest.NewServer(staticHandler(http.StatusOK, []byte("not-json{")))
	t.Cleanup(srv.Close)

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	_, err = api.DoJSON[samplePayload](c, req)
	require.Error(t, err)
	assert.ErrorIs(t, err, api.ErrDecodingResponse)
}

// --------------------------------------------------------------------------
// DoJSON – transport error
// --------------------------------------------------------------------------

func TestDoJSON_TransportError(t *testing.T) {
	// Point client at a server that is already closed.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {}))
	srv.Close() // close immediately so the request fails

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/", nil)
	require.NoError(t, err)

	_, err = api.DoJSON[samplePayload](c, req)
	require.Error(t, err)
	// Should NOT be wrapped as ErrDecodingResponse — it must be a transport error.
	assert.False(t, errors.Is(err, api.ErrDecodingResponse))
}

// --------------------------------------------------------------------------
// DoJSON – context cancellation
// --------------------------------------------------------------------------

func TestDoJSON_ContextCancelled(t *testing.T) {
	// Server that blocks until the test finishes (to ensure the client times
	// out via context, not the server completing the response).
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}))
	t.Cleanup(srv.Close)

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	req, err := c.NewRequest(ctx, http.MethodGet, "/", nil)
	require.NoError(t, err)

	_, err = api.DoJSON[samplePayload](c, req)
	require.Error(t, err)
	assert.False(t, errors.Is(err, api.ErrDecodingResponse))
}

// --------------------------------------------------------------------------
// DoJSON – URL resolution via relative path
// --------------------------------------------------------------------------

func TestDoJSON_RelativePath(t *testing.T) {
	want := samplePayload{ID: "xyz", Name: "relative-test"}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/runs", func(w http.ResponseWriter, _ *http.Request) {
		w.Write(okEnvelope(t, want)) //nolint:errcheck
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	c, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	got, err := api.DoJSON[samplePayload](c, req)
	require.NoError(t, err)
	assert.Equal(t, want, got)
}

// --------------------------------------------------------------------------
// WithHTTPClient option
// --------------------------------------------------------------------------

func TestWithHTTPClient_UsedForRequests(t *testing.T) {
	called := false
	transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		called = true
		body := okEnvelope(t, samplePayload{ID: "1", Name: "custom"})
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(string(body))),
		}, nil
	})

	hc := &http.Client{Transport: transport}
	c, err := api.New("https://argus.scylladb.com", api.WithHTTPClient(hc))
	require.NoError(t, err)

	req, err := c.NewRequest(context.Background(), http.MethodGet, "/api/v1/runs", nil)
	require.NoError(t, err)

	_, err = api.DoJSON[samplePayload](c, req)
	require.NoError(t, err)
	assert.True(t, called, "custom HTTP client should have been used")
}

// roundTripFunc allows building a custom http.RoundTripper from a plain func.
type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
