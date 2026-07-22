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

	userSvc *UserService

	releases  models.ReleaseList
	gridviews map[string]models.GridView
}

// NewPlannerService constructs a [PlannerService].
func NewPlannerService(client *api.Client, c *cache.Cache) *PlannerService {
	return &PlannerService{
		client:    client,
		cache:     c,
		userSvc:   NewUserService(client, c),
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

// getUsers returns the users map. User fetching and caching is owned by
// [UserService]; this shim delegates so a PlannerService and its UserService
// share a single fetch.
func (s *PlannerService) getUsers(ctx context.Context) (models.UsersMap, error) {
	return s.userSvc.getUsers(ctx)
}

// ResolveUserID resolves a username (exact, case-insensitive) to its UUID.
// It delegates to [UserService.ResolveUserID].
func (s *PlannerService) ResolveUserID(ctx context.Context, ref string) (string, error) {
	return s.userSvc.ResolveUserID(ctx, ref)
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
// Groups match by name, pretty name, or build_system_id (unique within a
// release). Tests resolve in priority order: (1) exact build_system_id,
// (2) group-qualified "group/test", (3) bare name (rejected when ambiguous,
// with a candidate list).
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
	t, err := resolveTestEntity(grid, ref)
	if err != nil {
		return "", err
	}
	return t.ID, nil
}

// ResolveTestBuildID resolves a release name and a single test reference to the
// test's build_system_id (the Jenkins job path the test-execution endpoints
// consume). The test reference uses the same priority as [ResolveEntityID]:
// exact build_system_id, group-qualified "group/test", then unique bare name.
//
// Unlike assignment resolution, a reference that names a group (not a single
// test) is rejected — a build targets exactly one job — with an
// [ErrEntityNotFound]-wrapped message. An ambiguous test reference aborts with
// [ErrAmbiguousEntity] and a candidate list so the user can disambiguate.
func (s *PlannerService) ResolveTestBuildID(ctx context.Context, releaseRef, testRef string) (string, error) {
	releaseID, err := s.ResolveReleaseID(ctx, releaseRef)
	if err != nil {
		return "", err
	}
	grid, err := s.GetReleaseStructure(ctx, releaseID)
	if err != nil {
		return "", err
	}
	t, err := resolveTestEntity(grid, testRef)
	if err != nil {
		return "", err
	}
	return t.BuildSystemID, nil
}

// LabeledTest is a plan test selected by label: its group-qualified "group/test"
// reference, the build_system_id the test-execution endpoints consume, and the
// labels the underlying plan entity carries (for display).
type LabeledTest struct {
	Ref           string
	BuildSystemID string
	Labels        []string
}

// ResolveLabeledTests resolves a plan (by UUID or "releaseName#planNumber" key)
// and a set of labels to the plan's matching tests. A plan entity matches when
// its labels intersect the requested set (union), or — when matchAll is set —
// when it carries every requested label. Matching is case-insensitive.
//
// A matching test yields its own build_system_id; a matching group fans out to
// its enabled member tests. Entities no longer present in the release gridview
// (e.g. since disabled) are skipped. Results are de-duplicated by
// build_system_id and sorted by reference. When nothing matches, the error
// lists the labels actually present in the plan so the caller can correct a typo.
func (s *PlannerService) ResolveLabeledTests(ctx context.Context, planRef string, labels []string, matchAll bool) ([]LabeledTest, error) {
	if len(labels) == 0 {
		return nil, fmt.Errorf("at least one label is required")
	}
	plan, err := s.GetPlan(ctx, planRef)
	if err != nil {
		return nil, err
	}
	options, err := models.ParsePlanOptions(plan.Options)
	if err != nil {
		return nil, fmt.Errorf("parsing plan options: %w", err)
	}
	grid, err := s.GetReleaseStructure(ctx, plan.ReleaseID)
	if err != nil {
		return nil, err
	}

	// Wanted labels, lower-cased for case-insensitive matching.
	wanted := make(map[string]struct{}, len(labels))
	for _, l := range labels {
		wanted[strings.ToLower(l)] = struct{}{}
	}

	// Collect every distinct label seen in the plan, so an empty match can steer
	// the user toward a valid one.
	available := newOrderedSet()

	results := make([]LabeledTest, 0)
	seen := map[string]struct{}{} // dedup by build_system_id
	appendTest := func(t models.GridEntity, entityLabels []string) {
		if _, dup := seen[t.BuildSystemID]; dup {
			return
		}
		seen[t.BuildSystemID] = struct{}{}
		results = append(results, LabeledTest{
			Ref:           t.Group + "/" + t.Name,
			BuildSystemID: t.BuildSystemID,
			Labels:        append([]string(nil), entityLabels...),
		})
	}

	for entityID, opt := range options {
		for _, l := range opt.Labels {
			available.add(l)
		}
		if !labelsMatch(opt.Labels, wanted, matchAll) {
			continue
		}
		if t, ok := grid.Tests[entityID]; ok {
			appendTest(t, opt.Labels)
			continue
		}
		if _, ok := grid.Groups[entityID]; ok {
			// A labelled group fans out to its enabled member tests. Iterate the
			// gridview directly by group UUID (ExpandGroup resolves by name).
			for _, t := range grid.Tests {
				if t.GroupID == entityID && t.Enabled {
					appendTest(t, opt.Labels)
				}
			}
		}
		// Entity absent from the gridview (disabled/removed): skip.
	}

	if len(results) == 0 {
		if len(available.items) == 0 {
			return nil, fmt.Errorf("plan %q has no labelled tests", planRef)
		}
		sort.Strings(available.items)
		return nil, fmt.Errorf("no tests in plan %q match the requested labels; available labels: %s",
			planRef, strings.Join(available.items, ", "))
	}

	sort.Slice(results, func(i, j int) bool { return results[i].Ref < results[j].Ref })
	return results, nil
}

// labelsMatch reports whether an entity's labels satisfy the wanted set. With
// matchAll it requires every wanted label to be present (intersection == wanted);
// otherwise a single overlap suffices (union). Comparison is case-insensitive
// via the lower-cased wanted set.
func labelsMatch(entityLabels []string, wanted map[string]struct{}, matchAll bool) bool {
	if matchAll {
		have := make(map[string]struct{}, len(entityLabels))
		for _, l := range entityLabels {
			have[strings.ToLower(l)] = struct{}{}
		}
		for w := range wanted {
			if _, ok := have[w]; !ok {
				return false
			}
		}
		return true
	}
	for _, l := range entityLabels {
		if _, ok := wanted[strings.ToLower(l)]; ok {
			return true
		}
	}
	return false
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

// findGroup locates a group in the gridview by name, pretty name, or
// build_system_id (its fully-qualified "release/group" path), case-insensitively.
func findGroup(grid models.GridView, ref string) (models.GridEntity, error) {
	var matches []models.GridEntity
	for _, g := range grid.Groups {
		if strings.EqualFold(g.Name, ref) ||
			strings.EqualFold(g.PrettyName, ref) ||
			strings.EqualFold(g.BuildSystemID, ref) {
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

// resolveTestEntity implements the test resolution priority described on
// [PlannerService.ResolveEntityID], returning the matched gridview entity so
// callers can read either its UUID or its build_system_id.
func resolveTestEntity(grid models.GridView, ref string) (models.GridEntity, error) {
	// (1) exact build_system_id — globally unique, never ambiguous.
	for _, t := range grid.Tests {
		if t.BuildSystemID == ref {
			return t, nil
		}
	}

	// (2) group-qualified "group/test".
	if idx := strings.LastIndex(ref, "/"); idx != -1 {
		groupPart, testName := ref[:idx], ref[idx+1:]
		g, err := findGroup(grid, groupPart)
		switch {
		case err == nil:
			var matches []models.GridEntity
			for _, t := range grid.Tests {
				if t.GroupID == g.ID && strings.EqualFold(t.Name, testName) {
					matches = append(matches, t)
				}
			}
			if len(matches) == 1 {
				return matches[0], nil
			}
			if len(matches) > 1 {
				return models.GridEntity{}, fmt.Errorf("%w: ambiguous test %q within group %q (%d matches)", ErrAmbiguousEntity, testName, groupPart, len(matches))
			}
			return models.GridEntity{}, fmt.Errorf("%w: no test %q in group %q", ErrEntityNotFound, testName, groupPart)
		case errors.Is(err, ErrEntityNotFound):
			// The prefix isn't a known group; fall through to bare-name
			// resolution (the ref may be a plain name that contains a slash).
		default:
			// Ambiguous group prefix (or other error): surface it so callers
			// abort for disambiguation instead of misreporting "test not found".
			return models.GridEntity{}, err
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
		return matches[0], nil
	case 0:
		return models.GridEntity{}, fmt.Errorf("%w: no test %q in this release (use build_system_id or group/test)", ErrEntityNotFound, ref)
	default:
		return models.GridEntity{}, fmt.Errorf("%w: ambiguous test %q (%d matches): use build_system_id or group/test\n%s",
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
	// assignee mapping. "$owner" leaves the test unassigned (in tests only).
	// Labels attach to each resolved entity regardless of assignee.
	// Missing entity → warn and omit; bad user → abort.
	tests := newOrderedSet()
	assignments := map[string]string{}
	options := map[string]models.EntityOptions{}
	var missing []string
	for entityRef, value := range tmpl.Assignments {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				missing = append(missing, entityRef)
				warnings = append(warnings, fmt.Sprintf("test %q is not in release %q — omitted", entityRef, tmpl.Release))
				continue
			}
			return models.CreatePlanRequest{}, nil, err
		}

		labels := value.Labels()
		for _, id := range ids {
			tests.add(id)
			if len(labels) > 0 {
				options[id] = models.EntityOptions{Labels: append([]string(nil), labels...)}
			}
		}

		if value.Assignee == "" || value.Assignee == models.OwnerMarker {
			continue
		}

		userID, err := s.ResolveUserID(ctx, value.Assignee)
		if err != nil {
			return models.CreatePlanRequest{}, nil, fmt.Errorf("assignee %q: %w", value.Assignee, err)
		}
		for _, id := range ids {
			assignments[id] = userID
		}
	}

	// Participants are derived from the settled assignment map (assignees minus
	// the owner), not accumulated per-entry: when overlapping group/test entries
	// contend for a test, only the user who actually holds an assignment counts,
	// so a race loser is never left as a phantom participant. Sorted for a
	// deterministic payload.
	participantSet := map[string]bool{}
	for _, userID := range assignments {
		if userID != ownerID {
			participantSet[userID] = true
		}
	}
	participants := make([]string, 0, len(participantSet))
	for userID := range participantSet {
		participants = append(participants, userID)
	}
	sort.Strings(participants)

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
		Participants:  nonNilSlice(participants),
		TargetVersion: tmpl.TargetVersion,
		ReleaseID:     releaseID,
		Tests:         nonNilSlice(tests.items),
		Groups:        []string{},
		Assignments:   assignments,
		Options:       options,
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
	planOptions, err := models.ParsePlanOptions(plan.Options)
	if err != nil {
		return models.PlanTemplate{}, fmt.Errorf("parsing plan options: %w", err)
	}

	assignments := map[string]models.AssignmentValue{}

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
		assignments[name] = models.AssignmentValue{
			Assignee: u.Username,
			Options:  entityOptions(planOptions, entityID),
		}
	}

	// Remaining plan tests are unassigned: mark them "$owner" (they may still
	// carry labels).
	for _, t := range plan.Tests {
		name, ok := entityQualifiedName(grid, t)
		if !ok {
			continue
		}
		if _, exists := assignments[name]; !exists {
			assignments[name] = models.AssignmentValue{
				Assignee: models.OwnerMarker,
				Options:  entityOptions(planOptions, t),
			}
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

// entityOptions returns a copy of the per-entity options for id, or nil when
// the entity has no options (so an emitted [models.AssignmentValue] omits the
// options object entirely).
func entityOptions(options map[string]models.EntityOptions, id string) *models.EntityOptions {
	opt, ok := options[id]
	if !ok || len(opt.Labels) == 0 {
		return nil
	}
	return &models.EntityOptions{Labels: append([]string(nil), opt.Labels...)}
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
	// Options are non-fatal too: a malformed blob simply yields no labels.
	planOptions, _ := models.ParsePlanOptions(plan.Options)

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
	var assignments map[string]models.AssignmentValue
	for entityID, userID := range plan.AssigneeMapping {
		if assignments == nil {
			assignments = map[string]models.AssignmentValue{}
		}
		assignments[entityName(entityID)] = models.AssignmentValue{
			Assignee: username(userID),
			Options:  entityOptions(planOptions, entityID),
		}
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
//     As with tests, a group name matching nothing warns and is skipped while an
//     ambiguous name aborts.
//   - Participants resolve by username.
//   - AssigneeMappingSet (from --assign) and Assignments (the template-style
//     map) share merge/patch semantics: each keyed test/group is added to the
//     plan when missing (membership follows assignment) and (re)assigned, or
//     unassigned when the value is "$owner". A reference matching nothing in the
//     release is reported and skipped; an ambiguous one aborts. Groups fan out
//     to each enabled test. AssigneeMappingRemove (from --unassign) clears an
//     assignee — resolving each entity reference (groups fan out) — without
//     adding membership; tests not mentioned are left untouched.
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
	// A missing group name warns and is skipped (like tests); ambiguous aborts.
	for _, g := range spec.GroupsAdd {
		ids, err := s.ExpandGroup(ctx, releaseID, g)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				warnings = append(warnings, fmt.Sprintf("group %q to add is not in this release — skipped", g))
				continue
			}
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
	// A missing group name warns and is skipped (like tests); ambiguous aborts.
	removeGroups := newOrderedSet()
	for _, g := range spec.GroupsRemove {
		id, err := s.ResolveEntityID(ctx, g, releaseID, KindGroup)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				warnings = append(warnings, fmt.Sprintf("group %q to remove is not in this release — skipped", g))
				continue
			}
			return models.PlanDiffRequest{}, nil, err
		}
		removeGroups.add(id)
	}
	if len(removeGroups.items) > 0 {
		diff.GroupsRemove = removeGroups.items
	}

	// Assignment application. The raw --assign / assignee_mapping_set map and the
	// template-style assignments map share identical merge/patch semantics: each
	// keyed test/group joins the plan (membership follows assignment) and is
	// (re)assigned, or is cleared — keeping the test — when the assignee is
	// "$owner". A template assignment value may also carry labels, applied as
	// additive label deltas (see below). Membership is ensured so the backend,
	// which drops mapping entries for tests not in plan.tests, keeps the
	// assignment instead of silently discarding it. A reference matching nothing
	// in the release is reported and skipped; an ambiguous one aborts so the user
	// can disambiguate.
	var assignSet map[string]string
	assignRemove := newOrderedSet()
	// Additive per-entity label deltas keyed by entity UUID, merged with the
	// entity's current labels below into a full options_set/options_remove diff.
	labelAdd := map[string]*orderedSet{}
	labelRemove := map[string]*orderedSet{}
	addLabel := func(store map[string]*orderedSet, id, label string) {
		set, ok := store[id]
		if !ok {
			set = newOrderedSet()
			store[id] = set
		}
		set.add(label)
	}

	applyAssignments := func(m map[string]models.AssignmentValue) error {
		for entityRef, value := range m {
			ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
			if err != nil {
				if errors.Is(err, ErrEntityNotFound) {
					warnings = append(warnings, fmt.Sprintf("assignment target %q is not in this release — skipped", entityRef))
					continue
				}
				return err
			}
			for _, id := range ids {
				addTests.add(id) // membership follows assignment/labels
			}
			for _, label := range value.Labels() {
				for _, id := range ids {
					addLabel(labelAdd, id, label)
				}
			}
			switch value.Assignee {
			case "":
				// Labels-only entry: no assignee change.
			case models.OwnerMarker:
				for _, id := range ids {
					assignRemove.add(id)
				}
			default:
				userID, err := s.ResolveUserID(ctx, value.Assignee)
				if err != nil {
					return fmt.Errorf("assignee %q: %w", value.Assignee, err)
				}
				for _, id := range ids {
					if assignSet == nil {
						assignSet = map[string]string{}
					}
					assignSet[id] = userID
				}
			}
		}
		return nil
	}

	// --assign feeds the string-valued assignee_mapping_set (assignee only,
	// unchanged behaviour): adapt it to the shared applier.
	if len(spec.AssigneeMappingSet) > 0 {
		converted := make(map[string]models.AssignmentValue, len(spec.AssigneeMappingSet))
		for ref, user := range spec.AssigneeMappingSet {
			converted[ref] = models.AssignmentValue{Assignee: user}
		}
		if err := applyAssignments(converted); err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
	}

	// Assignment removal (--unassign): resolve each entity (group fans out) to
	// its UUIDs and clear the assignee, keeping the test in the plan. Unlike
	// --assign this never adds membership — it only clears an existing mapping.
	for _, entityRef := range spec.AssigneeMappingRemove {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			assignRemove.add(id)
		}
	}

	if err := applyAssignments(spec.Assignments); err != nil {
		return models.PlanDiffRequest{}, nil, err
	}

	// --label adds labels (membership follows labels, like --assign); --unlabel
	// removes them without adding membership. Missing → warn/skip; ambiguous →
	// abort.
	for entityRef, labels := range spec.LabelsAdd {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				warnings = append(warnings, fmt.Sprintf("label target %q is not in this release — skipped", entityRef))
				continue
			}
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			addTests.add(id) // membership follows labels
			for _, label := range labels {
				addLabel(labelAdd, id, label)
			}
		}
	}
	for entityRef, labels := range spec.LabelsRemove {
		ids, err := s.resolveAssignmentTargets(ctx, entityRef, releaseID)
		if err != nil {
			if errors.Is(err, ErrEntityNotFound) {
				warnings = append(warnings, fmt.Sprintf("unlabel target %q is not in this release — skipped", entityRef))
				continue
			}
			return models.PlanDiffRequest{}, nil, err
		}
		for _, id := range ids {
			for _, label := range labels {
				addLabel(labelRemove, id, label)
			}
		}
	}

	diff.AssigneeMappingSet = assignSet

	// Merge label deltas with the plan's current labels into a full per-entity
	// options diff. An entity whose label set becomes empty is dropped via
	// options_remove; the backend applies removes before sets and prunes to the
	// plan's surviving entities.
	if err := s.applyOptionsDiff(&diff, plan, labelAdd, labelRemove); err != nil {
		return models.PlanDiffRequest{}, nil, err
	}

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

	// A plan must keep at least one test or group; refuse an edit that empties it.
	if planLeftEmpty(plan, addTests, removeTests, removeGroups) {
		return models.PlanDiffRequest{}, warnings, fmt.Errorf("update would remove the plan's last test or group; a plan must include at least one test")
	}

	return diff, warnings, nil
}

// applyOptionsDiff merges the additive per-entity label deltas (labelAdd,
// labelRemove, both keyed by entity UUID) with the plan's current labels and
// populates diff.OptionsSet / diff.OptionsRemove. For each touched entity the
// final label set is current ∪ adds − removes: a non-empty set is sent as a
// full options_set (the backend replaces the entity's option bag), while a set
// that becomes empty is sent as options_remove when the entity currently has
// options (otherwise it is a no-op and omitted).
func (s *PlannerService) applyOptionsDiff(diff *models.PlanDiffRequest, plan models.ReleasePlan, labelAdd, labelRemove map[string]*orderedSet) error {
	if len(labelAdd) == 0 && len(labelRemove) == 0 {
		return nil
	}
	current, err := models.ParsePlanOptions(plan.Options)
	if err != nil {
		return fmt.Errorf("parsing plan options: %w", err)
	}

	touched := map[string]struct{}{}
	for id := range labelAdd {
		touched[id] = struct{}{}
	}
	for id := range labelRemove {
		touched[id] = struct{}{}
	}

	var optionsSet map[string]models.EntityOptions
	var optionsRemove []string
	for id := range touched {
		removeSet := map[string]bool{}
		if rem, ok := labelRemove[id]; ok {
			for _, l := range rem.items {
				removeSet[l] = true
			}
		}
		final := newOrderedSet()
		for _, l := range current[id].Labels {
			if !removeSet[l] {
				final.add(l)
			}
		}
		if add, ok := labelAdd[id]; ok {
			for _, l := range add.items {
				if !removeSet[l] {
					final.add(l)
				}
			}
		}

		if len(final.items) == 0 {
			// Only emit a removal when the entity actually had options today.
			if _, had := current[id]; had {
				optionsRemove = append(optionsRemove, id)
			}
			continue
		}
		if optionsSet == nil {
			optionsSet = map[string]models.EntityOptions{}
		}
		optionsSet[id] = models.EntityOptions{Labels: final.items}
	}
	sort.Strings(optionsRemove)

	diff.OptionsSet = optionsSet
	if len(optionsRemove) > 0 {
		diff.OptionsRemove = optionsRemove
	}
	return nil
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

// planLeftEmpty reports whether applying the deltas would leave a plan with no
// membership at all. Membership is tests plus groups: tests shrink via
// removeTests and grow via addTests, while groups only shrink via removeGroups
// (the CLI always fans groups out to tests, so no groups are ever added). A
// plan that started empty of both is left alone — it is up to the add deltas to
// populate it.
func planLeftEmpty(plan models.ReleasePlan, addTests, removeTests, removeGroups *orderedSet) bool {
	if len(plan.Tests) == 0 && len(plan.Groups) == 0 {
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
	groups := map[string]bool{}
	for _, g := range plan.Groups {
		groups[g] = true
	}
	for _, g := range removeGroups.items {
		delete(groups, g)
	}
	return len(remaining) == 0 && len(groups) == 0
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
