package services

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
)

// RunFetcher abstracts the run-type resolution and typed fetch machinery that
// lives in the cmd package.  The services package uses this interface so it can
// resolve a test_id from a run without importing cmd (which would be circular).
type RunFetcher interface {
	// ResolveRunType returns the plugin type string (e.g. "generic",
	// "scylla-cluster-tests") for the given run ID.
	ResolveRunType(ctx context.Context, client *api.Client, runID string) (string, error)

	// FetchRun fetches the full run object for the given type and ID.  The
	// concrete type is preserved inside the returned any value.  The
	// implementation should check the cache first and populate it after a
	// network fetch.
	FetchRun(ctx context.Context, client *api.Client, c *cache.Cache, runType, runID string) (any, error)
}

// ExtractTestID marshals a run object to JSON and pulls out the test_id field.
// This avoids type-switching over every plugin type since they all embed RunBase.
func ExtractTestID(run any) (string, error) {
	raw, err := json.Marshal(run)
	if err != nil {
		return "", fmt.Errorf("extracting test_id: %w", err)
	}
	var partial struct {
		TestID string `json:"test_id"`
	}
	if err := json.Unmarshal(raw, &partial); err != nil {
		return "", fmt.Errorf("extracting test_id: %w", err)
	}
	if partial.TestID == "" {
		return "", fmt.Errorf("run object has no test_id field")
	}
	return partial.TestID, nil
}

// ResolveTestID returns testID from flagTestID if non-empty, otherwise uses the
// RunFetcher to look up the run and extract the test_id field automatically.
func ResolveTestID(
	ctx context.Context,
	client *api.Client,
	c *cache.Cache,
	fetcher RunFetcher,
	runID, flagTestID string,
) (string, error) {
	if flagTestID != "" {
		return flagTestID, nil
	}

	runType, err := fetcher.ResolveRunType(ctx, client, runID)
	if err != nil {
		return "", fmt.Errorf("resolving test_id: %w", err)
	}

	run, err := fetcher.FetchRun(ctx, client, c, runType, runID)
	if err != nil {
		return "", fmt.Errorf("fetching run for test_id: %w", err)
	}

	return ExtractTestID(run)
}

// defaultRunFetcher implements RunFetcher using function references so the cmd
// package can wire in its own handlers without the services package knowing
// about them.
type defaultRunFetcher struct {
	resolveRunType func(ctx context.Context, client *api.Client, runID string) (string, error)
	fetchRun       func(ctx context.Context, client *api.Client, c *cache.Cache, runType, runID string) (any, error)
}

func (f *defaultRunFetcher) ResolveRunType(ctx context.Context, client *api.Client, runID string) (string, error) {
	return f.resolveRunType(ctx, client, runID)
}

func (f *defaultRunFetcher) FetchRun(ctx context.Context, client *api.Client, c *cache.Cache, runType, runID string) (any, error) {
	return f.fetchRun(ctx, client, c, runType, runID)
}

// NewRunFetcher constructs a [RunFetcher] from the provided callback functions.
// This allows the cmd package to supply its run-type handler registry without
// creating a circular import.
func NewRunFetcher(
	resolveRunType func(ctx context.Context, client *api.Client, runID string) (string, error),
	fetchRun func(ctx context.Context, client *api.Client, c *cache.Cache, runType, runID string) (any, error),
) RunFetcher {
	return &defaultRunFetcher{
		resolveRunType: resolveRunType,
		fetchRun:       fetchRun,
	}
}
