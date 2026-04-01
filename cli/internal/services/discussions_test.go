package services_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// jsonOK wraps payload in the standard Argus API envelope.
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

func stubComments() []models.Comment {
	return []models.Comment{
		{
			ID: "c1", TestRunID: "run-1", UserID: "user-1",
			ReleaseID: "rel-1", TestID: "test-1", PostedAt: 1700000000,
			Message: "first", Mentions: []string{}, Reactions: map[string]int{},
		},
		{
			ID: "c2", TestRunID: "run-1", UserID: "user-2",
			ReleaseID: "rel-1", TestID: "test-1", PostedAt: 1700000001,
			Message: "second", Mentions: []string{"user-1"}, Reactions: map[string]int{"thumbsup": 1},
		},
	}
}

func noopFetcher(t *testing.T) services.RunFetcher {
	t.Helper()
	return services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, _ string) (string, error) {
			t.Fatal("should not be called")
			return "", nil
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, _, _ string) (any, error) {
			t.Fatal("should not be called")
			return nil, nil
		},
	)
}

// --------------------------------------------------------------------------
// SubmitComment
// --------------------------------------------------------------------------

func TestDiscussionService_SubmitComment(t *testing.T) {
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
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	svc := services.NewDiscussionService(client, ca, noopFetcher(t))

	result, err := svc.SubmitComment(context.Background(), "test-1", "run-1", "hello world", []string{"user-2"})
	require.NoError(t, err)

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comments/submit", gotPath)
	assert.Equal(t, "hello world", gotBody.Message)
	assert.Equal(t, []string{"user-2"}, gotBody.Mentions)
	assert.Len(t, result, 2)
}

func TestDiscussionService_SubmitComment_NilMentions(t *testing.T) {
	t.Parallel()

	var gotBody models.CommentSubmitRequest

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/test/test-1/run/run-1/comments/submit", func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		require.NoError(t, json.Unmarshal(raw, &gotBody))
		jsonOK(t, w, stubComments())
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	svc := services.NewDiscussionService(client, ca, noopFetcher(t))

	_, err = svc.SubmitComment(context.Background(), "test-1", "run-1", "no mentions", nil)
	require.NoError(t, err)

	// nil mentions should be normalised to [].
	assert.NotNil(t, gotBody.Mentions)
	assert.Empty(t, gotBody.Mentions)
}

// --------------------------------------------------------------------------
// UpdateComment
// --------------------------------------------------------------------------

func TestDiscussionService_UpdateComment(t *testing.T) {
	t.Parallel()
	comments := stubComments()
	comments[0].Message = "updated"

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
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	svc := services.NewDiscussionService(client, ca, noopFetcher(t))

	result, err := svc.UpdateComment(context.Background(), "test-1", "run-1", "c1", "updated", []string{})
	require.NoError(t, err)

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comment/c1/update", gotPath)
	assert.Equal(t, "updated", gotBody.Message)
	assert.Len(t, result, 2)
	assert.Equal(t, "updated", result[0].Message)
}

// --------------------------------------------------------------------------
// DeleteComment
// --------------------------------------------------------------------------

func TestDiscussionService_DeleteComment(t *testing.T) {
	t.Parallel()
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
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	svc := services.NewDiscussionService(client, ca, noopFetcher(t))

	result, err := svc.DeleteComment(context.Background(), "test-1", "run-1", "c1")
	require.NoError(t, err)

	assert.Equal(t, "POST", gotMethod)
	assert.Equal(t, "/api/v1/test/test-1/run/run-1/comment/c1/delete", gotPath)
	assert.Empty(t, gotBodyBytes)
	assert.Len(t, result, 1)
	assert.Equal(t, "c2", result[0].ID)
}

// --------------------------------------------------------------------------
// ResolveTestID delegation
// --------------------------------------------------------------------------

func TestDiscussionService_ResolveTestID_UsesFlag(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	svc := services.NewDiscussionService(client, ca, noopFetcher(t))

	got, err := svc.ResolveTestID(context.Background(), "run-1", "explicit-id")
	require.NoError(t, err)
	assert.Equal(t, "explicit-id", got)
}

func TestDiscussionService_ResolveTestID_DelegatesToFetcher(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	fetcher := services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, runID string) (string, error) {
			assert.Equal(t, "run-1", runID)
			return "generic", nil
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, runType, runID string) (any, error) {
			return models.GenericRun{
				RunBase: models.RunBase{ID: runID, TestID: "resolved-id"},
			}, nil
		},
	)

	svc := services.NewDiscussionService(client, ca, fetcher)

	got, err := svc.ResolveTestID(context.Background(), "run-1", "")
	require.NoError(t, err)
	assert.Equal(t, "resolved-id", got)
}
