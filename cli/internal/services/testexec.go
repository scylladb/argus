package services

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"time"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// ErrNoBuildsAvailable is returned (wrapped) by [TestExecutionService.FetchParams]
// when the backend reports that a job has no builds and no default parameter
// definitions to seed from (the "#noBuildsAvailable" signal). Callers decide
// whether that is fatal (`test params`) or recoverable (`test execute`, which
// proceeds with empty defaults supplied by --file/--param).
var ErrNoBuildsAvailable = errors.New("no builds available for this job")

// noBuildsSignal is the sentinel message the backend's JenkinsService raises
// when a job has neither historical builds nor default parameter definitions.
const noBuildsSignal = "#noBuildsAvailable"

// Default polling behaviour for [TestExecutionService.WaitForBuild].
const (
	defaultWaitTimeout  = 5 * time.Minute
	defaultWaitInterval = 3 * time.Second
)

// TestExecutionService drives the Jenkins-backed test-execution endpoints:
// fetching a job's parameters, triggering a build, and inspecting the resulting
// queue item. Tests are addressed by build_system_id (the Jenkins job path);
// the backend derives the requesting user from the authenticated session.
type TestExecutionService struct {
	client *api.Client
	cache  *cache.Cache
}

// NewTestExecutionService constructs a [TestExecutionService].
func NewTestExecutionService(client *api.Client, c *cache.Cache) *TestExecutionService {
	return &TestExecutionService{client: client, cache: c}
}

// FetchParams returns the parameter set for the job identified by buildID
// (a build_system_id). buildNumber selects which historical build's parameters
// to seed from; nil means "the last build, falling back to job defaults".
//
// When the job has no builds and no default definitions, the backend signals
// "#noBuildsAvailable"; FetchParams maps that to [ErrNoBuildsAvailable] so
// callers can distinguish it from a genuine failure.
func (s *TestExecutionService) FetchParams(ctx context.Context, buildID string, buildNumber *int) ([]models.JenkinsParameter, error) {
	body := models.JenkinsParamsRequest{BuildID: buildID, BuildNumber: buildNumber}
	req, err := s.client.NewRequest(ctx, "POST", api.JenkinsParams, body)
	if err != nil {
		return nil, err
	}
	resp, err := api.DoJSON[models.JenkinsParamsResponse](s.client, req)
	if err != nil {
		if isNoBuildsError(err) {
			return nil, fmt.Errorf("%w: %q", ErrNoBuildsAvailable, buildID)
		}
		return nil, err
	}
	return resp.Parameters, nil
}

// TriggerBuild schedules a build of the job identified by buildID with the
// given parameters and returns the Jenkins queue item number.
func (s *TestExecutionService) TriggerBuild(ctx context.Context, buildID string, params map[string]any) (int, error) {
	if params == nil {
		params = map[string]any{}
	}
	body := models.JenkinsBuildRequest{BuildID: buildID, Parameters: params}
	req, err := s.client.NewRequest(ctx, "POST", api.JenkinsBuild, body)
	if err != nil {
		return 0, err
	}
	resp, err := api.DoJSON[models.JenkinsBuildResponse](s.client, req)
	if err != nil {
		return 0, err
	}
	return resp.QueueItem, nil
}

// QueueInfo returns the current state of a Jenkins queue item: either the
// scheduled build (with URL) or the pending-queue reason.
func (s *TestExecutionService) QueueInfo(ctx context.Context, queueItem int) (models.JenkinsQueueInfo, error) {
	params := url.Values{}
	params.Set("queueItem", fmt.Sprint(queueItem))
	route := api.JenkinsQueueInfo + "?" + params.Encode()
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return models.JenkinsQueueInfo{}, err
	}
	return api.DoJSON[models.JenkinsQueueInfo](s.client, req)
}

// WaitForBuild polls QueueInfo until the queue item is scheduled onto an
// executor (its build URL is known), the timeout elapses, or ctx is cancelled.
// A zero timeout or interval falls back to the package defaults.
func (s *TestExecutionService) WaitForBuild(ctx context.Context, queueItem int, timeout, interval time.Duration) (models.JenkinsQueueInfo, error) {
	if timeout <= 0 {
		timeout = defaultWaitTimeout
	}
	if interval <= 0 {
		interval = defaultWaitInterval
	}

	deadline := time.Now().Add(timeout)
	var last models.JenkinsQueueInfo
	for {
		info, err := s.QueueInfo(ctx, queueItem)
		if err != nil {
			return last, err
		}
		last = info
		if info.Scheduled() {
			return info, nil
		}
		if time.Now().After(deadline) {
			return last, fmt.Errorf("timed out after %s waiting for queue item %d to start", timeout, queueItem)
		}

		select {
		case <-ctx.Done():
			return last, ctx.Err()
		case <-time.After(interval):
		}
	}
}

// MergeParams computes the final parameter map for a build using the cascade
// defaults < file < flags: it starts from the fetched job defaults, overlays
// the --file map, then overlays the --param flag map (each level overriding the
// previous by key). Nil overlays are ignored. The result is always non-nil.
func MergeParams(defaults []models.JenkinsParameter, file, flags map[string]any) map[string]any {
	merged := make(map[string]any, len(defaults))
	for _, p := range defaults {
		merged[p.Name] = p.Value
	}
	for k, v := range file {
		merged[k] = v
	}
	for k, v := range flags {
		merged[k] = v
	}
	return merged
}

// isNoBuildsError reports whether err carries the backend's "#noBuildsAvailable"
// signal (surfaced through the APIError envelope).
func isNoBuildsError(err error) bool {
	var apiErr *api.APIError
	if errors.As(err, &apiErr) {
		if apiErr.Body.Message == noBuildsSignal {
			return true
		}
		for _, arg := range apiErr.Body.Arguments {
			if arg == noBuildsSignal {
				return true
			}
		}
	}
	return false
}
