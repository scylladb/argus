package services_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestExecSvc(t *testing.T, mux *http.ServeMux) *services.TestExecutionService {
	t.Helper()
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	client, err := api.New(srv.URL, api.WithHTTPClient(srv.Client()))
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))
	return services.NewTestExecutionService(client, ca)
}

func TestMergeParams_Cascade(t *testing.T) {
	defaults := []models.JenkinsParameter{
		{Name: "backend", Value: "aws"},
		{Name: "region", Value: "us-east-1"},
		{Name: "keep", Value: "always"},
	}
	file := map[string]any{"region": "eu-west-1", "extra": "from-file"}
	flags := map[string]any{"backend": "gce", "extra": "from-flag"}

	merged := services.MergeParams(defaults, file, flags)

	// defaults < file < flags: flags win over file, file wins over defaults,
	// untouched defaults are preserved.
	assert.Equal(t, "gce", merged["backend"])      // flag overrides default
	assert.Equal(t, "eu-west-1", merged["region"]) // file overrides default
	assert.Equal(t, "always", merged["keep"])      // default preserved
	assert.Equal(t, "from-flag", merged["extra"])  // flag overrides file
}

func TestMergeParams_EmptyOverlays(t *testing.T) {
	defaults := []models.JenkinsParameter{{Name: "a", Value: "1"}}
	merged := services.MergeParams(defaults, nil, nil)
	assert.Equal(t, map[string]any{"a": "1"}, merged)

	// No defaults, only overlays.
	merged = services.MergeParams(nil, map[string]any{"b": "2"}, nil)
	assert.Equal(t, map[string]any{"b": "2"}, merged)
}

func TestFetchParams_Success(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/params", func(w http.ResponseWriter, r *http.Request) {
		var body models.JenkinsParamsRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		assert.Equal(t, "scylla/longevity", body.BuildID)
		assert.Nil(t, body.BuildNumber)
		jsonOK(t, w, models.JenkinsParamsResponse{Parameters: []models.JenkinsParameter{
			{Name: "backend", Value: "aws", Choices: []string{"aws", "gce"}},
		}})
	})
	svc := newTestExecSvc(t, mux)

	params, err := svc.FetchParams(context.Background(), "scylla/longevity", nil)
	require.NoError(t, err)
	require.Len(t, params, 1)
	assert.Equal(t, "backend", params[0].Name)
	assert.Equal(t, []string{"aws", "gce"}, params[0].Choices)
}

func TestFetchParams_BuildNumberSent(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/params", func(w http.ResponseWriter, r *http.Request) {
		var body models.JenkinsParamsRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		require.NotNil(t, body.BuildNumber)
		assert.Equal(t, 42, *body.BuildNumber)
		jsonOK(t, w, models.JenkinsParamsResponse{})
	})
	svc := newTestExecSvc(t, mux)

	n := 42
	_, err := svc.FetchParams(context.Background(), "scylla/longevity", &n)
	require.NoError(t, err)
}

func TestFetchParams_NoBuildsAvailable(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/params", func(w http.ResponseWriter, _ *http.Request) {
		jsonErr(t, w, "#noBuildsAvailable")
	})
	svc := newTestExecSvc(t, mux)

	_, err := svc.FetchParams(context.Background(), "scylla/longevity", nil)
	require.Error(t, err)
	assert.True(t, errors.Is(err, services.ErrNoBuildsAvailable))
}

func TestTriggerBuild(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/build", func(w http.ResponseWriter, r *http.Request) {
		var body models.JenkinsBuildRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		assert.Equal(t, "scylla/longevity", body.BuildID)
		assert.Equal(t, "eu-west-1", body.Parameters["region"])
		jsonOK(t, w, models.JenkinsBuildResponse{QueueItem: 777})
	})
	svc := newTestExecSvc(t, mux)

	item, err := svc.TriggerBuild(context.Background(), "scylla/longevity", map[string]any{"region": "eu-west-1"})
	require.NoError(t, err)
	assert.Equal(t, 777, item)
}

func TestTriggerBuild_NilParams(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/build", func(w http.ResponseWriter, r *http.Request) {
		var body models.JenkinsBuildRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&body))
		// nil params must serialise as an empty object, not null.
		assert.NotNil(t, body.Parameters)
		jsonOK(t, w, models.JenkinsBuildResponse{QueueItem: 1})
	})
	svc := newTestExecSvc(t, mux)

	_, err := svc.TriggerBuild(context.Background(), "scylla/longevity", nil)
	require.NoError(t, err)
}

func TestQueueInfo(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/queue_info", func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "777", r.URL.Query().Get("queueItem"))
		jsonOK(t, w, models.JenkinsQueueInfo{URL: "https://jenkins/job/x/12/", Number: 12})
	})
	svc := newTestExecSvc(t, mux)

	info, err := svc.QueueInfo(context.Background(), 777)
	require.NoError(t, err)
	assert.True(t, info.Scheduled())
	assert.Equal(t, "https://jenkins/job/x/12/", info.URL)
}

func TestWaitForBuild_PollsUntilScheduled(t *testing.T) {
	var calls int
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/queue_info", func(w http.ResponseWriter, _ *http.Request) {
		calls++
		if calls < 2 {
			jsonOK(t, w, models.JenkinsQueueInfo{Why: "waiting", TaskURL: "https://jenkins/job/x/"})
			return
		}
		jsonOK(t, w, models.JenkinsQueueInfo{URL: "https://jenkins/job/x/12/", Number: 12})
	})
	svc := newTestExecSvc(t, mux)

	info, err := svc.WaitForBuild(context.Background(), 777, time.Second, time.Millisecond)
	require.NoError(t, err)
	assert.True(t, info.Scheduled())
	assert.GreaterOrEqual(t, calls, 2)
}

func TestWaitForBuild_Timeout(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jenkins/queue_info", func(w http.ResponseWriter, _ *http.Request) {
		jsonOK(t, w, models.JenkinsQueueInfo{Why: "waiting"})
	})
	svc := newTestExecSvc(t, mux)

	_, err := svc.WaitForBuild(context.Background(), 777, 20*time.Millisecond, time.Millisecond)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "timed out")
}

func TestIsValidationError(t *testing.T) {
	// A backend DataValidationError is recognised as a terminal validation
	// failure, even when wrapped.
	verr := &api.APIError{Body: models.ErrorBody{Exception: "DataValidationError", Message: "bad"}}
	assert.True(t, services.IsValidationError(verr))
	assert.True(t, services.IsValidationError(fmt.Errorf("wrapped: %w", verr)))

	// Other API errors and plain errors are not validation failures.
	assert.False(t, services.IsValidationError(&api.APIError{Body: models.ErrorBody{Exception: "SomeOtherError"}}))
	assert.False(t, services.IsValidationError(errors.New("boom")))
	assert.False(t, services.IsValidationError(nil))
}
