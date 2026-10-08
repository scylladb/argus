package services

import (
	"context"
	"fmt"
	"net/url"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/models"
)

// IssueService backs the `issue runs` command: it looks up the runs linked to
// an issue key. Responses are not cached, so a link added a moment ago shows.
type IssueService struct {
	client *api.Client
}

// NewIssueService constructs an [IssueService].
func NewIssueService(client *api.Client) *IssueService {
	return &IssueService{client: client}
}

// Links returns the issue held under key and the runs linked to it, newest
// first. The server uppercases the key and rejects one that fits no tracker's
// key format; a well-formed key Argus does not hold yields a nil Issue and no
// links.
func (s *IssueService) Links(ctx context.Context, key string) (models.IssueLinks, error) {
	req, err := s.client.NewRequest(ctx, "GET", fmt.Sprintf(api.IssueLinks, url.PathEscape(key)), nil)
	if err != nil {
		return models.IssueLinks{}, err
	}
	return api.DoJSON[models.IssueLinks](s.client, req)
}
