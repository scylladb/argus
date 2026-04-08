package services_test

import (
	"context"
	"fmt"
	"testing"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
	"github.com/scylladb/argus/cli/internal/services"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --------------------------------------------------------------------------
// ExtractTestID
// --------------------------------------------------------------------------

func TestExtractTestID_FromRunBase(t *testing.T) {
	t.Parallel()
	run := models.RunBase{ID: "run-1", TestID: "test-abc"}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "test-abc", got)
}

func TestExtractTestID_FromSCTTestRun(t *testing.T) {
	t.Parallel()
	run := models.SCTTestRun{
		RunBase: models.RunBase{ID: "run-1", TestID: "test-sct"},
	}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "test-sct", got)
}

func TestExtractTestID_FromGenericRun(t *testing.T) {
	t.Parallel()
	run := models.GenericRun{
		RunBase: models.RunBase{ID: "run-2", TestID: "test-generic"},
	}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "test-generic", got)
}

func TestExtractTestID_FromDriverTestRun(t *testing.T) {
	t.Parallel()
	run := models.DriverTestRun{
		RunBase: models.RunBase{ID: "run-3", TestID: "test-driver"},
	}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "test-driver", got)
}

func TestExtractTestID_FromSirenadaRun(t *testing.T) {
	t.Parallel()
	run := models.SirenadaRun{
		RunBase: models.RunBase{ID: "run-4", TestID: "test-sirenada"},
	}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "test-sirenada", got)
}

func TestExtractTestID_EmptyTestID(t *testing.T) {
	t.Parallel()
	run := models.RunBase{ID: "run-5", TestID: ""}
	_, err := services.ExtractTestID(run)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "test_id")
}

func TestExtractTestID_MapWithTestID(t *testing.T) {
	t.Parallel()
	// Any JSON-marshalable value with test_id should work.
	run := map[string]string{"test_id": "from-map", "id": "run-6"}
	got, err := services.ExtractTestID(run)
	require.NoError(t, err)
	assert.Equal(t, "from-map", got)
}

func TestExtractTestID_NonMarshalableValue(t *testing.T) {
	t.Parallel()
	// Channels can't be marshaled to JSON.
	_, err := services.ExtractTestID(make(chan int))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "extracting test_id")
}

// --------------------------------------------------------------------------
// ResolveTestID
// --------------------------------------------------------------------------

func TestResolveTestID_ShortCircuitsOnFlag(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	fetcher := services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, _ string) (string, error) {
			t.Fatal("resolveRunType should not be called")
			return "", nil
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, _, _ string) (any, error) {
			t.Fatal("fetchRun should not be called")
			return nil, nil
		},
	)

	got, err := services.ResolveTestID(context.Background(), client, ca, fetcher, "run-1", "explicit-id")
	require.NoError(t, err)
	assert.Equal(t, "explicit-id", got)
}

func TestResolveTestID_DelegatesToFetcher(t *testing.T) {
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
			assert.Equal(t, "generic", runType)
			assert.Equal(t, "run-1", runID)
			return models.GenericRun{
				RunBase: models.RunBase{ID: "run-1", TestID: "resolved-id"},
			}, nil
		},
	)

	got, err := services.ResolveTestID(context.Background(), client, ca, fetcher, "run-1", "")
	require.NoError(t, err)
	assert.Equal(t, "resolved-id", got)
}

func TestResolveTestID_ResolveRunTypeError(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	fetcher := services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, _ string) (string, error) {
			return "", fmt.Errorf("network error")
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, _, _ string) (any, error) {
			t.Fatal("fetchRun should not be called")
			return nil, nil
		},
	)

	_, err = services.ResolveTestID(context.Background(), client, ca, fetcher, "run-1", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "network error")
}

func TestResolveTestID_FetchRunError(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	fetcher := services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, _ string) (string, error) {
			return "generic", nil
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, _, _ string) (any, error) {
			return nil, fmt.Errorf("server unavailable")
		},
	)

	_, err = services.ResolveTestID(context.Background(), client, ca, fetcher, "run-1", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "server unavailable")
}

func TestResolveTestID_RunMissingTestID(t *testing.T) {
	t.Parallel()
	client, err := api.New("http://localhost:0")
	require.NoError(t, err)
	ca := cache.New(t.TempDir(), cache.WithDisabled(true))

	fetcher := services.NewRunFetcher(
		func(_ context.Context, _ *api.Client, _ string) (string, error) {
			return "generic", nil
		},
		func(_ context.Context, _ *api.Client, _ *cache.Cache, _, _ string) (any, error) {
			// Return a run with no test_id.
			return models.RunBase{ID: "run-1", TestID: ""}, nil
		},
	)

	_, err = services.ResolveTestID(context.Background(), client, ca, fetcher, "run-1", "")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "test_id")
}
