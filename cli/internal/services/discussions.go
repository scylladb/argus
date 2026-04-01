package services

import (
	"context"
	"fmt"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// DiscussionService encapsulates business logic for comment operations
// (submit, update, delete) on test run discussions.
type DiscussionService struct {
	client  *api.Client
	cache   *cache.Cache
	fetcher RunFetcher
}

// NewDiscussionService constructs a [DiscussionService].
func NewDiscussionService(client *api.Client, c *cache.Cache, fetcher RunFetcher) *DiscussionService {
	return &DiscussionService{
		client:  client,
		cache:   c,
		fetcher: fetcher,
	}
}

// ResolveTestID returns flagTestID when non-empty, otherwise delegates to
// the package-level [ResolveTestID] using the service's RunFetcher.
func (s *DiscussionService) ResolveTestID(ctx context.Context, runID, flagTestID string) (string, error) {
	return ResolveTestID(ctx, s.client, s.cache, s.fetcher, runID, flagTestID)
}

// SubmitComment posts a new comment on the specified test run and returns the
// updated comment list.
func (s *DiscussionService) SubmitComment(
	ctx context.Context,
	testID, runID, message string,
	mentions []string,
) (models.CommentListResponse, error) {
	body := models.CommentSubmitRequest{
		Message:   message,
		Reactions: map[string]int{},
		Mentions:  mentions,
	}
	if body.Mentions == nil {
		body.Mentions = []string{}
	}

	route := fmt.Sprintf(api.TestRunCommentSubmit, testID, runID)
	req, err := s.client.NewRequest(ctx, "POST", route, body)
	if err != nil {
		return nil, err
	}
	result, err := api.DoJSON[models.CommentListResponse](s.client, req)
	if err != nil {
		return nil, err
	}

	_ = s.cache.Invalidate(cache.RunCommentsKey(runID))

	return result, nil
}

// UpdateComment edits an existing comment and returns the updated comment list.
func (s *DiscussionService) UpdateComment(
	ctx context.Context,
	testID, runID, commentID, message string,
	mentions []string,
) (models.CommentListResponse, error) {
	body := models.CommentSubmitRequest{
		Message:   message,
		Reactions: map[string]int{},
		Mentions:  mentions,
	}
	if body.Mentions == nil {
		body.Mentions = []string{}
	}

	route := fmt.Sprintf(api.TestRunCommentUpdate, testID, runID, commentID)
	req, err := s.client.NewRequest(ctx, "POST", route, body)
	if err != nil {
		return nil, err
	}
	result, err := api.DoJSON[models.CommentListResponse](s.client, req)
	if err != nil {
		return nil, err
	}

	_ = s.cache.Invalidate(cache.RunCommentsKey(runID))
	_ = s.cache.Invalidate(cache.CommentKey(commentID))

	return result, nil
}

// DeleteComment removes a comment and returns the updated comment list.
func (s *DiscussionService) DeleteComment(
	ctx context.Context,
	testID, runID, commentID string,
) (models.CommentListResponse, error) {
	route := fmt.Sprintf(api.TestRunCommentDelete, testID, runID, commentID)
	req, err := s.client.NewRequest(ctx, "POST", route, nil)
	if err != nil {
		return nil, err
	}
	result, err := api.DoJSON[models.CommentListResponse](s.client, req)
	if err != nil {
		return nil, err
	}

	_ = s.cache.Invalidate(cache.RunCommentsKey(runID))
	_ = s.cache.Invalidate(cache.CommentKey(commentID))

	return result, nil
}
