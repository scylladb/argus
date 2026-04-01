package cmd_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/scylladb/argus/cli/cmd"
	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/output"
	"github.com/spf13/cobra"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------

// jsonOK wraps payload in the standard Argus API envelope and writes it as
// a JSON response with status 200.
func jsonOK(t *testing.T, w http.ResponseWriter, payload any) {
	t.Helper()
	raw, err := json.Marshal(payload)
	require.NoError(t, err)
	env := map[string]json.RawMessage{
		"status":   json.RawMessage(`"ok"`),
		"response": raw,
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	require.NoError(t, json.NewEncoder(w).Encode(env))
}

// stubComments returns a sample comment list for testing.
func stubComments() []models.Comment {
	return []models.Comment{
		{
			ID:        "c1",
			TestRunID: "run-1",
			UserID:    "user-1",
			ReleaseID: "rel-1",
			TestID:    "test-1",
			PostedAt:  1700000000,
			Message:   "first comment",
			Mentions:  []string{},
			Reactions: map[string]int{},
		},
		{
			ID:        "c2",
			TestRunID: "run-1",
			UserID:    "user-2",
			ReleaseID: "rel-1",
			TestID:    "test-1",
			PostedAt:  1700000001,
			Message:   "second comment",
			Mentions:  []string{"user-1"},
			Reactions: map[string]int{"thumbsup": 1},
		},
	}
}

// newTestContext builds a context wired with the given API client, a JSON
// outputter that writes to buf, and a disabled cache.
func newTestContext(t *testing.T, client *api.Client, buf *bytes.Buffer) context.Context {
	t.Helper()
	ctx := context.Background()
	ctx = cmd.ContextWithAPIClient(ctx, client)
	ctx = cmd.ContextWithOutputter(ctx, output.New(buf, false))
	ctx = cmd.ContextWithCache(ctx, cache.New(t.TempDir(), cache.WithDisabled(true)))
	return ctx
}

// --------------------------------------------------------------------------
// extractTestID
// --------------------------------------------------------------------------

func TestExtractTestID_FromSCTRun(t *testing.T) {
	t.Parallel()
	run := models.SCTTestRun{
		RunBase: models.RunBase{
			ID:     "run-1",
			TestID: "test-abc",
		},
	}
	got, err := cmd.ExtractTestIDFn(run)
	require.NoError(t, err)
	assert.Equal(t, "test-abc", got)
}

func TestExtractTestID_FromGenericRun(t *testing.T) {
	t.Parallel()
	run := models.GenericRun{
		RunBase: models.RunBase{
			ID:     "run-2",
			TestID: "test-xyz",
		},
	}
	got, err := cmd.ExtractTestIDFn(run)
	require.NoError(t, err)
	assert.Equal(t, "test-xyz", got)
}

func TestExtractTestID_EmptyTestID(t *testing.T) {
	t.Parallel()
	run := models.RunBase{ID: "run-3", TestID: ""}
	_, err := cmd.ExtractTestIDFn(run)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "test_id")
}

// --------------------------------------------------------------------------
// parseMentions
// --------------------------------------------------------------------------

func TestParseMentions_Empty(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	got := cmd.ParseMentionsFn(c)
	assert.Nil(t, got)
}

func TestParseMentions_Single(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1"))
	got := cmd.ParseMentionsFn(c)
	assert.Equal(t, []string{"user-1"}, got)
}

func TestParseMentions_Multiple(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1, user-2,user-3"))
	got := cmd.ParseMentionsFn(c)
	assert.Equal(t, []string{"user-1", "user-2", "user-3"}, got)
}

func TestParseMentions_IgnoresEmptySegments(t *testing.T) {
	t.Parallel()
	c := &cobra.Command{}
	c.Flags().String("mention", "", "")
	require.NoError(t, c.Flags().Set("mention", "user-1,,, user-2,"))
	got := cmd.ParseMentionsFn(c)
	assert.Equal(t, []string{"user-1", "user-2"}, got)
}

// --------------------------------------------------------------------------
// resolveTestID
// --------------------------------------------------------------------------

func TestResolveTestID_UsesProvidedFlag(t *testing.T) {
	t.Parallel()
	// No server needed — the flag value is returned directly.
	c, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	got, err := cmd.ResolveTestIDFn(context.Background(), c, ca, "run-1", "explicit-test-id")
	require.NoError(t, err)
	assert.Equal(t, "explicit-test-id", got)
}

func TestResolveTestID_ResolvesFromServer(t *testing.T) {
	t.Parallel()

	// We need two endpoints: get-type and get-run.
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/run/run-1/type", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.RunType{RunType: "generic"})
	})
	mux.HandleFunc("/api/v1/run/generic/run-1", func(w http.ResponseWriter, _ *http.Request) {
		run := models.GenericRun{
			RunBase: models.RunBase{ID: "run-1", TestID: "resolved-test-id"},
		}
		jsonOK(t, w, run)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	got, err := cmd.ResolveTestIDFn(context.Background(), client, ca, "run-1", "")
	require.NoError(t, err)
	assert.Equal(t, "resolved-test-id", got)
}

// --------------------------------------------------------------------------
// comment submit
// --------------------------------------------------------------------------

func TestCommentSubmit_Success(t *testing.T) {
	t.Parallel()
	comments := stubComments()

	var gotBody models.CommentSubmitRequest
	var gotMethod, gotPath string

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/test/test-1/run/run-1/comments/submit", func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		require.NoError(t, json.Unmarshal(raw, &gotBody))
		jsonOK(t, w, comments)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	var buf bytes.Buffer
	ctx := newTestContext(t, client, &buf)

	c := &cobra.Command{Use: "submit", RunE: func(cmd *cobra.Command, _ []string) error { return nil }}
	c.Flags().String("run-id", "run-1", "")
	c.Flags().String("test-id", "test-1", "")
	c.Flags().String("message", "hello world", "")
	c.Flags().String("mention", "user-2", "")
	c.SetContext(ctx)

	// Directly invoke the internals — we reuse the same flow the real command does.
	runID, _ := c.Flags().GetString("run-id")
	testID, _ := c.Flags().GetString("test-id")
	message, _ := c.Flags().GetString("message")

	body := models.CommentSubmitRequest{
		Message:   message,
		Reactions: map[string]int{},
		Mentions:  cmd.ParseMentionsFn(c),
	}

	route := "/api/v1/test/" + testID + "/run/" + runID + "/comments/submit"
	req, err := client.NewRequest(ctx, "POST", route, body)
	require.NoError(t, err)
	result, err := api.DoJSON[models.CommentListResponse](client, req)
	require.NoError(t, err)

	out := output.New(&buf, false)
	require.NoError(t, out.Write(models.NewTabularSlice(result)))

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comments/submit", gotPath)
	assert.Equal(t, "hello world", gotBody.Message)
	assert.Equal(t, []string{"user-2"}, gotBody.Mentions)
	assert.Len(t, result, 2)
}

// --------------------------------------------------------------------------
// comment update
// --------------------------------------------------------------------------

func TestCommentUpdate_Success(t *testing.T) {
	t.Parallel()
	comments := stubComments()
	// Modify the first comment to reflect the update.
	comments[0].Message = "updated message"

	var gotBody models.CommentSubmitRequest
	var gotMethod, gotPath string

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/test/test-1/run/run-1/comment/c1/update", func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		raw, _ := io.ReadAll(r.Body)
		require.NoError(t, json.Unmarshal(raw, &gotBody))
		jsonOK(t, w, comments)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	var buf bytes.Buffer
	ctx := newTestContext(t, client, &buf)

	body := models.CommentSubmitRequest{
		Message:   "updated message",
		Reactions: map[string]int{},
		Mentions:  []string{},
	}

	route := "/api/v1/test/test-1/run/run-1/comment/c1/update"
	req, err := client.NewRequest(ctx, "POST", route, body)
	require.NoError(t, err)
	result, err := api.DoJSON[models.CommentListResponse](client, req)
	require.NoError(t, err)

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comment/c1/update", gotPath)
	assert.Equal(t, "updated message", gotBody.Message)
	assert.Len(t, result, 2)
	assert.Equal(t, "updated message", result[0].Message)
}

// --------------------------------------------------------------------------
// comment delete
// --------------------------------------------------------------------------

func TestCommentDelete_Success(t *testing.T) {
	t.Parallel()
	// After deletion, only the second comment remains.
	remaining := stubComments()[1:]

	var gotMethod, gotPath string
	var gotBodyBytes []byte

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/test/test-1/run/run-1/comment/c1/delete", func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotBodyBytes, _ = io.ReadAll(r.Body)
		jsonOK(t, w, remaining)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)

	var buf bytes.Buffer
	ctx := newTestContext(t, client, &buf)

	route := "/api/v1/test/test-1/run/run-1/comment/c1/delete"
	req, err := client.NewRequest(ctx, "POST", route, nil)
	require.NoError(t, err)
	result, err := api.DoJSON[models.CommentListResponse](client, req)
	require.NoError(t, err)

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comment/c1/delete", gotPath)
	// Delete sends no body.
	assert.Empty(t, gotBodyBytes)
	assert.Len(t, result, 1)
	assert.Equal(t, "c2", result[0].ID)
}

// --------------------------------------------------------------------------
// CommentSubmitRequest serialisation
// --------------------------------------------------------------------------

func TestCommentSubmitRequest_JSON(t *testing.T) {
	t.Parallel()
	req := models.CommentSubmitRequest{
		Message:   "test message",
		Reactions: map[string]int{"thumbsup": 1},
		Mentions:  []string{"user-1", "user-2"},
	}

	raw, err := json.Marshal(req)
	require.NoError(t, err)

	var got models.CommentSubmitRequest
	require.NoError(t, json.Unmarshal(raw, &got))
	assert.Equal(t, req, got)
}

func TestCommentSubmitRequest_EmptyMentions(t *testing.T) {
	t.Parallel()
	req := models.CommentSubmitRequest{
		Message:   "no mentions",
		Reactions: map[string]int{},
		Mentions:  []string{},
	}

	raw, err := json.Marshal(req)
	require.NoError(t, err)

	// Ensure mentions serialises as [] not null.
	assert.Contains(t, string(raw), `"mentions":[]`)
}

// --------------------------------------------------------------------------
// API route constants
// --------------------------------------------------------------------------

func TestRouteConstants_Format(t *testing.T) {
	t.Parallel()

	assert.Contains(t, api.TestRunCommentSubmit, "/comments/submit")
	assert.Contains(t, api.TestRunCommentUpdate, "/comment/%s/update")
	assert.Contains(t, api.TestRunCommentDelete, "/comment/%s/delete")
}

// --------------------------------------------------------------------------
// Integration: resolveTestID fallback with real HTTP
// --------------------------------------------------------------------------

func TestResolveTestID_FailsOnBadRunType(t *testing.T) {
	t.Parallel()

	mux := http.NewServeMux()
	// Return a run type that's not in the handler map.
	mux.HandleFunc("/api/v1/run/run-1/type", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.RunType{RunType: "unknown-plugin"})
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	_, err = cmd.ResolveTestIDFn(context.Background(), client, ca, "run-1", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unknown run type")
}
