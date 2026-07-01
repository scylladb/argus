package services

import (
	"context"
	"errors"
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

// Resolution sentinel errors. They let callers distinguish a reference that
// matched nothing (safe to warn-and-omit on create) from one that matched
// several candidates (must abort so the user disambiguates).
var (
	// ErrEntityNotFound is returned (wrapped) when a test/group reference
	// matches no entity in the release.
	ErrEntityNotFound = errors.New("entity not found in release")
	// ErrAmbiguousEntity is returned (wrapped) when a reference matches more
	// than one entity and cannot be resolved safely.
	ErrAmbiguousEntity = errors.New("ambiguous entity reference")
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
// Search (discovery)
// ---------------------------------------------------------------------------

// Search queries the planning search endpoint for tests/groups/releases
// matching query, optionally scoped to a release (by name). The query string is
// passed through verbatim — see the search command help for the facet syntax.
//
// The synthetic "Add all..." special row the backend always prepends
// (type "special") is filtered out before returning. When releaseRef is empty
// the search spans all releases.
func (s *PlannerService) Search(ctx context.Context, query, releaseRef string) (models.SearchHitList, error) {
	params := url.Values{}
	params.Set("query", query)
	if releaseRef != "" {
		releaseID, err := s.ResolveReleaseID(ctx, releaseRef)
		if err != nil {
			return nil, err
		}
		params.Set("releaseId", releaseID)
	}

	route := api.PlanningSearch + "?" + params.Encode()
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	resp, err := api.DoJSON[models.SearchResponse](s.client, req)
	if err != nil {
		return nil, err
	}

	hits := make(models.SearchHitList, 0, len(resp.Hits))
	for _, h := range resp.Hits {
		if h.Type == "special" {
			continue
		}
		hits = append(hits, h)
	}
	return hits, nil
}

// ---------------------------------------------------------------------------
// Plan writes
// ---------------------------------------------------------------------------

// CreatePlan creates a release plan from a fully-resolved request (all
// references already converted to UUIDs by [PlannerService.BuildCreateRequest])
// and returns the created plan, including its server-assigned id and key.
func (s *PlannerService) CreatePlan(ctx context.Context, req models.CreatePlanRequest) (models.ReleasePlan, error) {
	r, err := s.client.NewRequest(ctx, "POST", api.PlanCreate, req)
	if err != nil {
		return models.ReleasePlan{}, err
	}
	return api.DoJSON[models.ReleasePlan](s.client, r)
}

// DeletePlan deletes the plan addressed by UUID id or "releaseName#planNumber"
// key. When deleteView is true the plan's associated view is deleted too;
// otherwise the view is detached and kept.
func (s *PlannerService) DeletePlan(ctx context.Context, planRef string, deleteView bool) error {
	// Plan keys contain '#'; escape so the ref survives URL parsing.
	route := fmt.Sprintf(api.PlanDelete, url.PathEscape(planRef))
	params := url.Values{}
	if deleteView {
		params.Set("deleteView", "1")
	} else {
		params.Set("deleteView", "0")
	}
	route += "?" + params.Encode()

	req, err := s.client.NewRequest(ctx, "DELETE", route, nil)
	if err != nil {
		return err
	}
	_, err = api.DoJSON[bool](s.client, req)
	return err
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

// GetReleaseOverview fetches the release gridview and returns a
// [models.ReleaseGrid] mapping each enabled test's group-qualified "group/test"
// reference to its build_system_id, for an at-a-glance overview of a release.
func (s *PlannerService) GetReleaseOverview(ctx context.Context, releaseID string) (models.ReleaseGrid, error) {
	grid, err := s.GetReleaseStructure(ctx, releaseID)
	if err != nil {
		return nil, err
	}
	overview := make(models.ReleaseGrid, len(grid.Tests))
	for _, t := range grid.Tests {
		overview[t.Group+"/"+t.Name] = t.BuildSystemID
	}
	return overview, nil
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
		return models.GridEntity{}, fmt.Errorf("%w: no group named %q in this release", ErrEntityNotFound, ref)
	default:
		return models.GridEntity{}, fmt.Errorf("%w: ambiguous group name %q (%d matches)", ErrAmbiguousEntity, ref, len(matches))
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
				return "", fmt.Errorf("%w: ambiguous test %q within group %q (%d matches)", ErrAmbiguousEntity, testName, groupPart, len(matches))
			}
			return "", fmt.Errorf("%w: no test %q in group %q", ErrEntityNotFound, testName, groupPart)
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
		return "", fmt.Errorf("%w: no test %q in this release (use build_system_id or group/test)", ErrEntityNotFound, ref)
	default:
		return "", fmt.Errorf("%w: ambiguous test %q (%d matches): use build_system_id or group/test\n%s",
			ErrAmbiguousEntity, ref, len(matches), formatTestCandidates(matches))
	}
}

// formatTestCandidates renders ambiguous test matches as an indented list of
// build_system_id and group so the user can pick an unambiguous reference.
func formatTestCandidates(matches []models.GridEntity) string {
	sort.Slice(matches, func(i, j int) bool { return matches[i].BuildSystemID < matches[j].BuildSystemID })
	var b strings.Builder
	for _, t := range matches {
		fmt.Fprintf(&b, "  - %s (group: %s)\n", t.BuildSystemID, t.Group)
	}
	return strings.TrimRight(b.String(), "\n")
}

// formatBullets renders refs as an indented one-per-line bullet list for
// multi-entity error messages.
func formatBullets(refs []string) string {
	var b strings.Builder
	for _, r := range refs {
		fmt.Fprintf(&b, "  - %s\n", r)
	}
	return strings.TrimRight(b.String(), "\n")
}

// ---------------------------------------------------------------------------
// Create-from-template (BuildCreateRequest) and the get template transform
// ---------------------------------------------------------------------------

// orderedSet collects strings preserving first-insertion order while skipping
// duplicates — used to merge tests from multiple sources (explicit tests,
// expanded groups, assignment fan-out) deterministically.
type orderedSet struct {
	seen  map[string]struct{}
	items []string
}

func newOrderedSet() *orderedSet { return &orderedSet{seen: map[string]struct{}{}} }

func (o *orderedSet) add(v string) {
	if _, ok := o.seen[v]; ok {
		return
	}
	o.seen[v] = struct{}{}
	o.items = append(o.items, v)
}

// nonNilSlice returns an empty (non-nil) slice when s is nil, so JSON encodes
// it as [] rather than null. The backend iterates these lists and rejects a
// null (TypeError: 'NoneType' object is not iterable).
func nonNilSlice(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

// BuildCreateRequest turns a name-based [models.PlanTemplate] (plus any extra
// group references from --group) into a fully UUID-resolved
// [models.CreatePlanRequest]. Every name is resolved client-side against the
// target release; only UUIDs are placed in the request.
//
// Groups are always expanded to their enabled member tests and merged into the
// tests list (the request's groups field is left empty). An assignment whose
// key is a group fans out to each of that group's enabled tests. Tests that do
// not exist in the target release are returned as warnings and omitted; an
// ambiguous reference instead aborts with an error so the user can disambiguate.
func (s *PlannerService) BuildCreateRequest(ctx context.Context, tmpl models.PlanTemplate) (models.CreatePlanRequest, []string, error) {
	var warnings []string

	if tmpl.Release == "" {
		return models.CreatePlanRequest{}, nil, fmt.Errorf("a release is required (set 'release' in the file or pass --release)")
	}
	releaseID, err := s.ResolveReleaseID(ctx, tmpl.Release)
	if err != nil {
		return models.CreatePlanRequest{}, nil, err
	}

	if tmpl.Owner == "" {
		return models.CreatePlanRequest{}, nil, fmt.Errorf("an owner is required (set 'owner' in the file or pass --owner)")
	}
	ownerID, err := s.ResolveUserID(ctx, tmpl.Owner)
	if err != nil {
		return models.CreatePlanRequest{}, nil, err
	}

	// Assignments are the single source of plan membership. Each entry's
	// targets join the tests list; a specific assignee also enters the
	// assignee mapping and becomes a participant. "$owner" leaves the test
	// unassigned (in tests only). Missing entity → warn and omit; bad user
	// → abort.
	tests := newOrderedSet()
	assignments := map[string]string{}
	participants := newOrderedSet()
	var missing []string
	for entityRef, userRef := range tmpl.Assignments {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				missing = append(missing, entityRef)
				warnings = append(warnings, fmt.Sprintf("test %q is not in release %q — omitted", entityRef, tmpl.Release))
				continue
			}
			return models.CreatePlanRequest{}, nil, err
		}

		if userRef == models.OwnerMarker {
			for _, id := range ids {
				tests.add(id)
			}
			continue
		}

		userID, err := s.ResolveUserID(ctx, userRef)
		if err != nil {
			return models.CreatePlanRequest{}, nil, fmt.Errorf("assignee %q: %w", userRef, err)
		}
		for _, id := range ids {
			tests.add(id)
			assignments[id] = userID
		}
		if userID != ownerID {
			participants.add(userID)
		}
	}

	// A plan must contain at least one test/group; refuse to create an empty
	// plan and list what could not be resolved (one per line).
	if len(tests.items) == 0 {
		sort.Strings(missing)
		if len(missing) > 0 {
			return models.CreatePlanRequest{}, warnings, fmt.Errorf(
				"no tests resolved in release %q; none of the assigned entities exist there:\n%s",
				tmpl.Release, formatBullets(missing))
		}
		return models.CreatePlanRequest{}, warnings, fmt.Errorf("a plan must include at least one test or group")
	}

	return models.CreatePlanRequest{
		Name:          tmpl.Name,
		Description:   tmpl.Description,
		Owner:         ownerID,
		Participants:  nonNilSlice(participants.items),
		TargetVersion: tmpl.TargetVersion,
		ReleaseID:     releaseID,
		Tests:         nonNilSlice(tests.items),
		Groups:        []string{},
		Assignments:   assignments,
	}, warnings, nil
}

// resolveAssignmentTargets resolves an assignment entity reference to the test
// UUIDs it applies to: a test reference yields itself; a group reference fans
// out to its enabled tests.
func (s *PlannerService) resolveAssignmentTargets(ctx context.Context, entityRef, releaseID string) ([]string, error) {
	id, err := s.ResolveEntityID(ctx, entityRef, releaseID, KindTest)
	if err == nil {
		return []string{id}, nil
	}
	if !errors.Is(err, ErrEntityNotFound) {
		return nil, err
	}
	// Not a test — try a group and fan out to its enabled tests. An ambiguous
	// group name must abort (so the user disambiguates); only a genuine miss is
	// reported as "not a test or group".
	ids, gerr := s.ExpandGroup(ctx, releaseID, entityRef)
	if gerr != nil {
		if errors.Is(gerr, ErrAmbiguousEntity) {
			return nil, gerr
		}
		return nil, fmt.Errorf("%q is not a test or group in release: %w", entityRef, ErrEntityNotFound)
	}
	return ids, nil
}

// BuildTemplate converts a stored plan (UUID-based) into a release-independent,
// human-readable [models.PlanTemplate]. Assignments is the single membership
// source: every test is keyed by its group-qualified "group/test" name and
// valued by the assignee username, or by [models.OwnerMarker] ("$owner") when
// the test is in the plan but has no specific assignee. It is the data behind
// the default `planner get` output.
//
// Names are back-resolved from the plan's own release gridview and the users
// list. Tests no longer present in that gridview (e.g. since disabled) cannot
// be named and are skipped.
func (s *PlannerService) BuildTemplate(ctx context.Context, plan models.ReleasePlan) (models.PlanTemplate, error) {
	releaseName, err := s.releaseNameByID(ctx, plan.ReleaseID)
	if err != nil {
		return models.PlanTemplate{}, err
	}
	users, err := s.getUsers(ctx)
	if err != nil {
		return models.PlanTemplate{}, err
	}
	grid, err := s.GetReleaseStructure(ctx, plan.ReleaseID)
	if err != nil {
		return models.PlanTemplate{}, err
	}

	assignments := map[string]string{}

	// Assigned tests carry their assignee username.
	for entityID, userID := range plan.AssigneeMapping {
		name, ok := entityQualifiedName(grid, entityID)
		if !ok {
			continue
		}
		u, ok := users[userID]
		if !ok {
			continue
		}
		assignments[name] = u.Username
	}

	// Remaining plan tests are unassigned: mark them "$owner".
	for _, t := range plan.Tests {
		name, ok := entityQualifiedName(grid, t)
		if !ok {
			continue
		}
		if _, exists := assignments[name]; !exists {
			assignments[name] = models.OwnerMarker
		}
	}

	tmpl := models.PlanTemplate{
		Name:          plan.Name,
		Description:   plan.Description,
		Release:       releaseName,
		TargetVersion: plan.TargetVersion,
		Assignments:   assignments,
	}
	if u, ok := users[plan.Owner]; ok {
		tmpl.Owner = u.Username
	}
	return tmpl, nil
}

// entityQualifiedName returns the "group/test" name for a test UUID, or the
// group name for a group UUID, found in the gridview. ok is false when the id
// is in neither map.
func entityQualifiedName(grid models.GridView, id string) (string, bool) {
	if t, ok := grid.Tests[id]; ok {
		return t.Group + "/" + t.Name, true
	}
	if g, ok := grid.Groups[id]; ok {
		return g.Name, true
	}
	return "", false
}

// releaseNameByID returns the name of the release with the given UUID.
func (s *PlannerService) releaseNameByID(ctx context.Context, releaseID string) (string, error) {
	releases, err := s.getReleases(ctx)
	if err != nil {
		return "", err
	}
	for _, r := range releases {
		if r.ID == releaseID {
			return r.Name, nil
		}
	}
	return "", fmt.Errorf("release id %q not found", releaseID)
}

// ---------------------------------------------------------------------------
// Resolved plan view (default get/list output)
// ---------------------------------------------------------------------------

// BuildResolvedPlan turns a stored plan (UUID-based) into a human-readable
// [models.ResolvedPlan]: release/owner/participant names, tests and assignment
// targets as group-qualified "group/test" strings, and groups as names, while
// keeping the plan's identity and status fields.
//
// It is the data behind `planner get --resolved` and the default `list`
// output. Unlike
// [PlannerService.BuildTemplate] it is lossless: any reference that cannot be
// resolved (a user not in the users list, or a test/group not in the release
// gridview) falls back to its raw UUID rather than being dropped, and an
// unknown release id is shown verbatim rather than failing the command.
func (s *PlannerService) BuildResolvedPlan(ctx context.Context, plan models.ReleasePlan) (models.ResolvedPlan, error) {
	users, err := s.getUsers(ctx)
	if err != nil {
		return models.ResolvedPlan{}, err
	}
	grid, err := s.GetReleaseStructure(ctx, plan.ReleaseID)
	if err != nil {
		return models.ResolvedPlan{}, err
	}
	// A missing release name is non-fatal for a display command — fall back to
	// the raw id so the rest of the plan still renders.
	releaseName, err := s.releaseNameByID(ctx, plan.ReleaseID)
	if err != nil {
		releaseName = plan.ReleaseID
	}

	username := func(id string) string {
		if u, ok := users[id]; ok {
			return u.Username
		}
		return id
	}
	entityName := func(id string) string {
		if name, ok := entityQualifiedName(grid, id); ok {
			return name
		}
		return id
	}

	participants := make([]string, 0, len(plan.Participants))
	for _, p := range plan.Participants {
		participants = append(participants, username(p))
	}
	tests := make([]string, 0, len(plan.Tests))
	for _, t := range plan.Tests {
		tests = append(tests, entityName(t))
	}
	groups := make([]string, 0, len(plan.Groups))
	for _, g := range plan.Groups {
		groups = append(groups, entityName(g))
	}
	var assignments map[string]string
	for entityID, userID := range plan.AssigneeMapping {
		if assignments == nil {
			assignments = map[string]string{}
		}
		assignments[entityName(entityID)] = username(userID)
	}

	return models.ResolvedPlan{
		ID:            plan.ID,
		Key:           plan.Key,
		Name:          plan.Name,
		Description:   plan.Description,
		Release:       releaseName,
		TargetVersion: plan.TargetVersion,
		Owner:         username(plan.Owner),
		Participants:  participants,
		Tests:         tests,
		Groups:        groups,
		Assignments:   assignments,
		Completed:     plan.Completed,
		ViewID:        plan.ViewID,
		CreatedFrom:   plan.CreatedFrom,
		CreationTime:  plan.CreationTime,
		LastUpdated:   plan.LastUpdated,
		EndsAt:        plan.EndsAt,
	}, nil
}

// BuildPlanSummaries resolves a slice of plans into the per-plan list view
// ([models.PlanSummary]): release/owner names come from the resolved plan,
// while tests/groups/participants are reported as counts taken from the source
// plan. Plans of the same release share the memoised gridview and users list,
// so a whole release's plan list resolves with at most one fetch of each.
func (s *PlannerService) BuildPlanSummaries(ctx context.Context, plans models.ReleasePlanList) ([]models.PlanSummary, error) {
	summaries := make([]models.PlanSummary, 0, len(plans))
	for _, p := range plans {
		rp, err := s.BuildResolvedPlan(ctx, p)
		if err != nil {
			return nil, err
		}
		summaries = append(summaries, models.PlanSummary{
			Key:           rp.Key,
			Name:          rp.Name,
			Description:   rp.Description,
			Release:       rp.Release,
			TargetVersion: rp.TargetVersion,
			Owner:         rp.Owner,
			Tests:         len(p.Tests),
			Groups:        len(p.Groups),
			Participants:  len(p.Participants),
			LastUpdated:   rp.LastUpdated,
		})
	}
	return summaries, nil
}

// ---------------------------------------------------------------------------
// Plan update (diff-based)
// ---------------------------------------------------------------------------

// UpdatePlan applies a fully-resolved diff (all references already converted to
// UUIDs by [PlannerService.BuildUpdateRequest]) to a plan via
// POST /planning/plan/update. The backend returns a boolean acknowledgement;
// the caller refetches the plan to display the new state.
func (s *PlannerService) UpdatePlan(ctx context.Context, req models.PlanDiffRequest) error {
	r, err := s.client.NewRequest(ctx, "POST", api.PlanUpdate, req)
	if err != nil {
		return err
	}
	_, err = api.DoJSON[bool](s.client, r)
	return err
}

// BuildUpdateRequest turns a name-based [models.PlanUpdateSpec] into the
// UUID-based [models.PlanDiffRequest] the backend expects, resolving every
// reference against the plan's own release. Only changed scalars and non-empty
// deltas are populated, so an unchanged field is never sent.
//
// Resolution rules mirror create:
//   - Scalar owner is a username resolved to a UUID; other scalars pass through.
//   - Tests in TestsAdd/TestsRemove resolve by build_system_id / "group/test" /
//     unique bare name. A reference matching nothing is reported as a warning
//     and omitted; an ambiguous reference aborts so the user can disambiguate.
//   - GroupsAdd is always expanded to the group's enabled tests (merged into
//     tests_add); no groups_add is ever sent. GroupsRemove resolves to a group
//     UUID and is sent as groups_remove (for groups still stored on the plan).
//   - Participants resolve by username.
//   - AssigneeMappingSet resolves the username value and the entity key (a test,
//     or a group fanned out to each enabled test); AssigneeMappingRemove resolves
//     each entity reference (group references fan out) to the UUIDs to drop.
//   - Assignments (the template-style map) is applied as a merge/patch: each
//     keyed test/group is added to the plan when missing and (re)assigned, or
//     unassigned when the value is "$owner". A reference matching nothing is
//     reported and skipped; tests not mentioned are left untouched.
func (s *PlannerService) BuildUpdateRequest(ctx context.Context, plan models.ReleasePlan, spec models.PlanUpdateSpec) (models.PlanDiffRequest, []string, error) {
	releaseID := plan.ReleaseID
	diff := models.PlanDiffRequest{ID: plan.ID}
	var warnings []string

	// Scalars — pass through, resolving owner username to a UUID.
	diff.Name = spec.Name
	diff.Description = spec.Description
	diff.TargetVersion = spec.TargetVersion
	diff.Completed = spec.Completed
	if spec.Owner != nil {
		ownerID, err := s.ResolveUserID(ctx, *spec.Owner)
		if err != nil {
			return models.PlanDiffRequest{}, nil, fmt.Errorf("owner %q: %w", *spec.Owner, err)
		}
		diff.Owner = &ownerID
	}

	// Test add/remove deltas. Missing → warn-and-omit; ambiguous → abort.
	addTests := newOrderedSet()
	for _, ref := range spec.TestsAdd {
		id, warn, err := s.resolveTestForDiff(ctx, ref, releaseID, "add")
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		if warn != "" {
			warnings = append(warnings, warn)
			continue
		}
		addTests.add(id)
	}
	// Groups added are always expanded to their enabled tests (no groups_add).
	for _, g := range spec.GroupsAdd {
		ids, err := s.ExpandGroup(ctx, releaseID, g)
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			addTests.add(id)
		}
	}

	removeTests := newOrderedSet()
	for _, ref := range spec.TestsRemove {
		id, warn, err := s.resolveTestForDiff(ctx, ref, releaseID, "remove")
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		if warn != "" {
			warnings = append(warnings, warn)
			continue
		}
		removeTests.add(id)
	}
	if len(removeTests.items) > 0 {
		diff.TestsRemove = removeTests.items
	}

	// Group removals target groups still stored on the plan (e.g. web-created).
	removeGroups := newOrderedSet()
	for _, g := range spec.GroupsRemove {
		id, err := s.ResolveEntityID(ctx, g, releaseID, KindGroup)
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		removeGroups.add(id)
	}
	if len(removeGroups.items) > 0 {
		diff.GroupsRemove = removeGroups.items
	}

	// Assignment set: resolve user, then entity (group fans out to its tests).
	// A "$owner" value clears the assignee (test stays) by routing the targets
	// to the removal set instead of the mapping.
	var assignSet map[string]string
	assignRemove := newOrderedSet()
	for entityRef, userRef := range spec.AssigneeMappingSet {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		if userRef == models.OwnerMarker {
			for _, id := range ids {
				assignRemove.add(id)
			}
			continue
		}
		userID, err := s.ResolveUserID(ctx, userRef)
		if err != nil {
			return models.PlanDiffRequest{}, nil, fmt.Errorf("assignee %q: %w", userRef, err)
		}
		for _, id := range ids {
			if assignSet == nil {
				assignSet = map[string]string{}
			}
			assignSet[id] = userID
		}
	}

	// Assignment removal: resolve each entity (group fans out) to its UUIDs.
	for _, entityRef := range spec.AssigneeMappingRemove {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			assignRemove.add(id)
		}
	}

	// Template-style assignments (merge/patch): each keyed test/group is ensured
	// to be in the plan and (re)assigned, or unassigned on "$owner". A reference
	// matching nothing is reported and skipped; an ambiguous one aborts.
	for entityRef, userRef := range spec.Assignments {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				warnings = append(warnings, fmt.Sprintf("assignment target %q is not in this release — skipped", entityRef))
				continue
			}
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			addTests.add(id) // membership follows assignment
		}
		if userRef == models.OwnerMarker {
			for _, id := range ids {
				assignRemove.add(id)
			}
			continue
		}
		userID, err := s.ResolveUserID(ctx, userRef)
		if err != nil {
			return models.PlanDiffRequest{}, nil, fmt.Errorf("assignee %q: %w", userRef, err)
		}
		for _, id := range ids {
			if assignSet == nil {
				assignSet = map[string]string{}
			}
			assignSet[id] = userID
		}
	}
	diff.AssigneeMappingSet = assignSet

	if len(addTests.items) > 0 {
		diff.TestsAdd = addTests.items
	}
	if len(assignRemove.items) > 0 {
		diff.AssigneeMappingRemove = assignRemove.items
	}

	// Participants are derived from the resulting assignments: anyone assigned
	// other than the (possibly new) owner is a participant. Compute the final
	// state and emit only the deltas against the plan's current participants.
	ownerID := plan.Owner
	if diff.Owner != nil {
		ownerID = *diff.Owner
	}
	diff.ParticipantsAdd, diff.ParticipantsRemove = participantDeltas(
		plan, removeTests, removeGroups, assignSet, assignRemove, ownerID)

	// A plan must keep at least one test; refuse an edit that would empty it.
	if planLeftEmpty(plan, addTests, removeTests) {
		return models.PlanDiffRequest{}, warnings, fmt.Errorf("update would remove the plan's last test; a plan must include at least one test")
	}

	return diff, warnings, nil
}

// participantDeltas computes participants_add/remove so the stored participants
// equal the resulting assignees minus the owner. assignSet entries are added,
// assignRemove entries are dropped, and entries on removed tests/groups are
// dropped too (mirroring the backend's mapping cleanup).
func participantDeltas(plan models.ReleasePlan, removeTests, removeGroups *orderedSet, assignSet map[string]string, assignRemove *orderedSet, ownerID string) (add, remove []string) {
	removed := map[string]bool{}
	for _, id := range removeTests.items {
		removed[id] = true
	}
	for _, id := range removeGroups.items {
		removed[id] = true
	}
	for _, id := range assignRemove.items {
		removed[id] = true
	}

	final := map[string]string{}
	for entity, user := range plan.AssigneeMapping {
		if !removed[entity] {
			final[entity] = user
		}
	}
	for entity, user := range assignSet {
		final[entity] = user
	}

	desired := map[string]bool{}
	for _, user := range final {
		if user != ownerID {
			desired[user] = true
		}
	}
	current := map[string]bool{}
	for _, p := range plan.Participants {
		current[p] = true
	}

	addSet := newOrderedSet()
	for user := range desired {
		if !current[user] {
			addSet.add(user)
		}
	}
	for _, p := range plan.Participants {
		if !desired[p] && p != ownerID {
			remove = append(remove, p)
		}
	}
	return addSet.items, remove
}

// planLeftEmpty reports whether applying the test add/remove deltas would empty
// a plan that currently has tests. A plan that started empty is left alone (it
// is up to add deltas to populate it).
func planLeftEmpty(plan models.ReleasePlan, addTests, removeTests *orderedSet) bool {
	if len(plan.Tests) == 0 {
		return false
	}
	remaining := map[string]bool{}
	for _, t := range plan.Tests {
		remaining[t] = true
	}
	for _, t := range removeTests.items {
		delete(remaining, t)
	}
	for _, t := range addTests.items {
		remaining[t] = true
	}
	return len(remaining) == 0
}

// resolveTestForDiff resolves a single test reference for an add/remove delta.
// A reference matching nothing yields a warning (so the diff still applies the
// rest); an ambiguous reference returns an error so the user disambiguates.
// verb ("add"/"remove") is used only in the warning text.
func (s *PlannerService) resolveTestForDiff(ctx context.Context, ref, releaseID, verb string) (id, warn string, err error) {
	id, err = s.ResolveEntityID(ctx, ref, releaseID, KindTest)
	if err == nil {
		return id, "", nil
	}
	if errors.Is(err, ErrEntityNotFound) {
		return "", fmt.Sprintf("test %q to %s is not in this release — skipped", ref, verb), nil
	}
	return "", "", err
}
