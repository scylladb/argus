package services

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// UserService is the single owner of user fetching and caching. It backs the
// `users` command and provides the username→UUID resolution that
// [PlannerService] delegates to when turning human references into UUIDs.
//
// It memoises the users list for the lifetime of the service so that a single
// command resolves many references with at most one network fetch.
type UserService struct {
	client *api.Client
	cache  *cache.Cache

	users models.UsersMap
}

// NewUserService constructs a [UserService].
func NewUserService(client *api.Client, c *cache.Cache) *UserService {
	return &UserService{client: client, cache: c}
}

// getUsers returns the users map, memoised then disk-cached.
func (s *UserService) getUsers(ctx context.Context) (models.UsersMap, error) {
	if s.users != nil {
		return s.users, nil
	}
	if cached, _, err := cache.Get[models.UsersMap](s.cache, cache.UsersKey()); err == nil {
		s.users = cached
		return cached, nil
	}

	req, err := s.client.NewRequest(ctx, "GET", api.Users, nil)
	if err != nil {
		return nil, err
	}
	users, err := api.DoJSON[models.UsersMap](s.client, req)
	if err != nil {
		return nil, err
	}
	_ = cache.Set(s.cache, cache.UsersKey(), users, api.Users, cache.TTLUsers)
	s.users = users
	return users, nil
}

// ListUsers returns every user, sorted by username (case-insensitive) for
// stable output.
func (s *UserService) ListUsers(ctx context.Context) ([]models.User, error) {
	users, err := s.getUsers(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]models.User, 0, len(users))
	for _, u := range users {
		out = append(out, u)
	}
	sort.Slice(out, func(i, j int) bool {
		return strings.ToLower(out[i].Username) < strings.ToLower(out[j].Username)
	})
	return out, nil
}

// GetUser returns the single user whose field matches value (case-insensitive).
// field must be one of "username", "uuid", or "email". It errors when no user
// matches or when more than one does.
func (s *UserService) GetUser(ctx context.Context, field, value string) (models.User, error) {
	users, err := s.getUsers(ctx)
	if err != nil {
		return models.User{}, err
	}

	match := func(u models.User) bool {
		switch field {
		case "uuid":
			return strings.EqualFold(u.ID, value)
		case "email":
			return strings.EqualFold(u.Email, value)
		default: // username
			return strings.EqualFold(u.Username, value)
		}
	}

	var matches []models.User
	for _, u := range users {
		if match(u) {
			matches = append(matches, u)
		}
	}

	switch len(matches) {
	case 1:
		return matches[0], nil
	case 0:
		return models.User{}, fmt.Errorf("no user with %s %q", field, value)
	default:
		return models.User{}, fmt.Errorf("ambiguous %s %q (%d matches)", field, value, len(matches))
	}
}

// ResolveUserID resolves a username (exact, case-insensitive) to its UUID.
// Raw UUIDs are not accepted; 0 or >1 matches error with candidate usernames.
func (s *UserService) ResolveUserID(ctx context.Context, ref string) (string, error) {
	users, err := s.getUsers(ctx)
	if err != nil {
		return "", err
	}

	var matches []string
	for id, u := range users {
		if strings.EqualFold(u.Username, ref) {
			matches = append(matches, id)
		}
	}

	switch len(matches) {
	case 1:
		return matches[0], nil
	case 0:
		return "", fmt.Errorf("no user named %q", ref)
	default:
		return "", fmt.Errorf("ambiguous username %q (%d matches)", ref, len(matches))
	}
}
