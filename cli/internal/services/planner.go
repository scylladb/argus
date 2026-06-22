package services

import (
	"context"
	"fmt"
	"net/url"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// EntityKind identifies whether an entity reference denotes a test or a group
// when resolving names against a release's gridview.
type EntityKind string

const (
	// KindTest selects test resolution (build_system_id / group/test / bare name).
	KindTest EntityKind = "test"
	// KindGroup selects group resolution (group name within the release).
	KindGroup EntityKind = "group"
)

// PlannerService encapsulates release-plan reads and the client-side name
// resolution (release/user/test/group) that turns human references into the
// UUIDs the backend expects. Only UUIDs are ever sent to the backend.
//
// It memoises the releases list, users list, and per-release gridviews for the
// lifetime of the service so that a single command resolves many references
// with at most one network fetch of each.
type PlannerService struct {
	client *api.Client
	cache  *cache.Cache

	releases  models.ReleaseList
	users     models.UsersMap
	gridviews map[string]models.GridView
}

// NewPlannerService constructs a [PlannerService].
func NewPlannerService(client *api.Client, c *cache.Cache) *PlannerService {
	return &PlannerService{
		client:    client,
		cache:     c,
		gridviews: map[string]models.GridView{},
	}
}

// ---------------------------------------------------------------------------
// Plan reads
// ---------------------------------------------------------------------------

// GetPlansForRelease returns every release plan for the given release UUID.
func (s *PlannerService) GetPlansForRelease(ctx context.Context, releaseID string) (models.ReleasePlanList, error) {
	route := fmt.Sprintf(api.PlansForRelease, releaseID)
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	return api.DoJSON[models.ReleasePlanList](s.client, req)
}

// GetPlan returns a single plan addressed by UUID id or by its human-friendly
// "releaseName#planNumber" key. The reference is passed through verbatim and
// resolved server-side.
func (s *PlannerService) GetPlan(ctx context.Context, planRef string) (models.ReleasePlan, error) {
	// Plan keys contain '#' (e.g. "scylla-2026.2#3"); escape so it survives URL
	// parsing as a path segment rather than being treated as a fragment.
	route := fmt.Sprintf(api.PlanGet, url.PathEscape(planRef))
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return models.ReleasePlan{}, err
	}
	return api.DoJSON[models.ReleasePlan](s.client, req)
}

// ---------------------------------------------------------------------------
// Release resolution
// ---------------------------------------------------------------------------

// getReleases returns the full releases list (including disabled releases so
// plans on archived releases still resolve), memoised then disk-cached.
func (s *PlannerService) getReleases(ctx context.Context) (models.ReleaseList, error) {
	if s.releases != nil {
		return s.releases, nil
	}
	if cached, _, err := cache.Get[models.ReleaseList](s.cache, cache.ReleasesKey()); err == nil {
		s.releases = cached
		return cached, nil
	}

	route := api.Releases + "?all=1"
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	releases, err := api.DoJSON[models.ReleaseList](s.client, req)
	if err != nil {
		return nil, err
	}
	_ = cache.Set(s.cache, cache.ReleasesKey(), releases, route, cache.TTLReleases)
	s.releases = releases
	return releases, nil
}

// ResolveReleaseID resolves a release name (exact, case-insensitive) to its
// UUID. Raw UUIDs are not accepted as input — a value that matches no release
// name errors with the list of available releases.
func (s *PlannerService) ResolveReleaseID(ctx context.Context, ref string) (string, error) {
	releases, err := s.getReleases(ctx)
	if err != nil {
		return "", err
	}

	var matches []models.Release
	for _, r := range releases {
		if strings.EqualFold(r.Name, ref) {
			matches = append(matches, r)
		}
	}

	switch len(matches) {
	case 1:
		return matches[0].ID, nil
	case 0:
		return "", fmt.Errorf("no release named %q (use the exact release name, e.g. scylla-2026.2)", ref)
	default:
		return "", fmt.Errorf("ambiguous release name %q (%d matches)", ref, len(matches))
	}
}

// ---------------------------------------------------------------------------
// User resolution
// ---------------------------------------------------------------------------

// getUsers returns the users map, memoised then disk-cached.
func (s *PlannerService) getUsers(ctx context.Context) (models.UsersMap, error) {
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

// ResolveUserID resolves a username (exact, case-insensitive) to its UUID.
// Raw UUIDs are not accepted; 0 or >1 matches error with candidate usernames.
func (s *PlannerService) ResolveUserID(ctx context.Context, ref string) (string, error) {
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

// ---------------------------------------------------------------------------
// Gridview + test/group resolution
// ---------------------------------------------------------------------------

// GetReleaseStructure returns the gridview (enabled tests + groups) for a
// release in a single call, memoised then disk-cached.
func (s *PlannerService) GetReleaseStructure(ctx context.Context, releaseID string) (models.GridView, error) {
	if gv, ok := s.gridviews[releaseID]; ok {
		return gv, nil
	}
	key := cache.GridviewKey(releaseID)
	if cached, _, err := cache.Get[models.GridView](s.cache, key); err == nil {
		s.gridviews[releaseID] = cached
		return cached, nil
	}

	route := fmt.Sprintf(api.Gridview, releaseID)
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return models.GridView{}, err
	}
	gv, err := api.DoJSON[models.GridView](s.client, req)
	if err != nil {
		return models.GridView{}, err
	}
	_ = cache.Set(s.cache, key, gv, route, cache.TTLGridview)
	s.gridviews[releaseID] = gv
	return gv, nil
}

// ResolveEntityID resolves a test or group reference (by name or
// build_system_id) to its UUID within a release, using a single gridview fetch.
//
// Groups match by name (unique within a release). Tests resolve in priority
// order: (1) exact build_system_id, (2) group-qualified "group/test",
// (3) bare name (rejected when ambiguous, with a candidate list).
func (s *PlannerService) ResolveEntityID(ctx context.Context, ref, releaseID string, kind EntityKind) (string, error) {
	grid, err := s.GetReleaseStructure(ctx, releaseID)
	if err != nil {
		return "", err
	}
	if kind == KindGroup {
		g, err := findGroup(grid, ref)
		if err != nil {
			return "", err
		}
		return g.ID, nil
	}
	return resolveTest(grid, ref)
}

// ExpandGroup resolves a group reference and returns the UUIDs of its enabled
// member tests, taken from the gridview's enabled-only tests map (deliberately
// not testByGroup / explode, which include disabled tests). The result is
// sorted for deterministic output.
func (s *PlannerService) ExpandGroup(ctx context.Context, releaseID, groupRef string) ([]string, error) {
	grid, err := s.GetReleaseStructure(ctx, releaseID)
	if err != nil {
		return nil, err
	}
	g, err := findGroup(grid, groupRef)
	if err != nil {
		return nil, err
	}

	var ids []string
	for id, t := range grid.Tests {
		if t.GroupID == g.ID && t.Enabled {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	return ids, nil
}

// findGroup locates a group in the gridview by name (then pretty name),
// case-insensitively.
func findGroup(grid models.GridView, ref string) (models.GridEntity, error) {
	var matches []models.GridEntity
	for _, g := range grid.Groups {
		if strings.EqualFold(g.Name, ref) || strings.EqualFold(g.PrettyName, ref) {
			matches = append(matches, g)
		}
	}
	switch len(matches) {
	case 1:
		return matches[0], nil
	case 0:
		return models.GridEntity{}, fmt.Errorf("no group named %q in this release", ref)
	default:
		return models.GridEntity{}, fmt.Errorf("ambiguous group name %q (%d matches)", ref, len(matches))
	}
}

// resolveTest implements the test resolution priority described on
// [PlannerService.ResolveEntityID].
func resolveTest(grid models.GridView, ref string) (string, error) {
	// (1) exact build_system_id — globally unique, never ambiguous.
	for id, t := range grid.Tests {
		if t.BuildSystemID == ref {
			return id, nil
		}
	}

	// (2) group-qualified "group/test".
	if idx := strings.LastIndex(ref, "/"); idx != -1 {
		groupPart, testName := ref[:idx], ref[idx+1:]
		if g, err := findGroup(grid, groupPart); err == nil {
			var matches []string
			for id, t := range grid.Tests {
				if t.GroupID == g.ID && strings.EqualFold(t.Name, testName) {
					matches = append(matches, id)
				}
			}
			if len(matches) == 1 {
				return matches[0], nil
			}
			if len(matches) > 1 {
				return "", fmt.Errorf("ambiguous test %q within group %q (%d matches)", testName, groupPart, len(matches))
			}
			return "", fmt.Errorf("no test %q in group %q", testName, groupPart)
		}
	}

	// (3) bare name — resolve only when unique.
	var matches []models.GridEntity
	for _, t := range grid.Tests {
		if strings.EqualFold(t.Name, ref) {
			matches = append(matches, t)
		}
	}
	switch len(matches) {
	case 1:
		return matches[0].ID, nil
	case 0:
		return "", fmt.Errorf("no test %q in this release (use build_system_id or group/test)", ref)
	default:
		return "", fmt.Errorf("ambiguous test %q (%d matches): use build_system_id or group/test\n%s",
			ref, len(matches), formatTestCandidates(matches))
	}
}

// formatTestCandidates renders ambiguous test matches as an indented list of
// build_system_id, group, and UUID so the user can pick an unambiguous ref.
func formatTestCandidates(matches []models.GridEntity) string {
	sort.Slice(matches, func(i, j int) bool { return matches[i].BuildSystemID < matches[j].BuildSystemID })
	var b strings.Builder
	for _, t := range matches {
		fmt.Fprintf(&b, "  - %s (group: %s, id: %s)\n", t.BuildSystemID, t.Group, t.ID)
	}
	return strings.TrimRight(b.String(), "\n")
}
