package services

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strings"

	"github.com/scylladb/argus/cli/internal/api"
	"github.com/scylladb/argus/cli/internal/cache"
	"github.com/scylladb/argus/cli/internal/models"
)

// ViewService encapsulates user-view reads and writes plus the client-side
// reference resolution they need. Views span many releases, so entity
// references (view items and widget filters) are release-qualified
// build_system_id paths resolved via the embedded [PlannerService.ResolveGlobalRef];
// only UUIDs are ever sent to the backend.
type ViewService struct {
	client  *api.Client
	cache   *cache.Cache
	planner *PlannerService
}

// NewViewService constructs a [ViewService]. It owns a [PlannerService] for the
// shared release/user/entity resolution (and its memoisation).
func NewViewService(client *api.Client, c *cache.Cache) *ViewService {
	return &ViewService{
		client:  client,
		cache:   c,
		planner: NewPlannerService(client, c),
	}
}

// uuidPattern matches a canonical 8-4-4-4-12 hexadecimal UUID, used to tell a
// raw view id apart from a view name (slug) in --view.
var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

// looksLikeUUID reports whether s is a canonical UUID string.
func looksLikeUUID(s string) bool {
	return uuidPattern.MatchString(strings.TrimSpace(s))
}

// viewWebURL builds the web address that opens a view in Argus, mirroring the
// backend route "/view/<view_name>" (see argus.backend.controller.main). An
// empty name yields an empty string.
func (s *ViewService) viewWebURL(name string) string {
	if strings.TrimSpace(name) == "" {
		return ""
	}
	return strings.TrimRight(s.client.BaseURL(), "/") + "/view/" + url.PathEscape(name)
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

// ListViews returns every view, optionally scoped to a single owner. userRef is
// a username (resolved to a UUID); an empty userRef lists all views.
func (s *ViewService) ListViews(ctx context.Context, userRef string) (models.ViewList, error) {
	route := api.ViewAll
	if userRef != "" {
		userID, err := s.planner.ResolveUserID(ctx, userRef)
		if err != nil {
			return nil, err
		}
		params := url.Values{}
		params.Set("userId", userID)
		route += "?" + params.Encode()
	}
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return nil, err
	}
	return api.DoJSON[models.ViewList](s.client, req)
}

// GetView returns a single view addressed by ref (a UUID or a view name).
func (s *ViewService) GetView(ctx context.Context, ref string) (models.View, error) {
	viewID, err := s.resolveViewRef(ctx, ref)
	if err != nil {
		return models.View{}, err
	}
	params := url.Values{}
	params.Set("viewId", viewID)
	route := api.ViewGet + "?" + params.Encode()
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return models.View{}, err
	}
	return api.DoJSON[models.View](s.client, req)
}

// getResolvedView fetches the resolve-for-edit payload for a view UUID (items
// decorated with build_system_id / name), used to reverse-map membership.
func (s *ViewService) getResolvedView(ctx context.Context, viewID string) (models.ResolvedView, error) {
	route := fmt.Sprintf(api.ViewResolve, url.PathEscape(viewID))
	req, err := s.client.NewRequest(ctx, "GET", route, nil)
	if err != nil {
		return models.ResolvedView{}, err
	}
	return api.DoJSON[models.ResolvedView](s.client, req)
}

// resolveViewRef resolves a view reference to its UUID. A canonical UUID passes
// through unchanged; otherwise ref is treated as a view name (slug) and matched
// against the full views list, erroring with candidate names on a miss.
func (s *ViewService) resolveViewRef(ctx context.Context, ref string) (string, error) {
	if looksLikeUUID(ref) {
		return ref, nil
	}
	views, err := s.ListViews(ctx, "")
	if err != nil {
		return "", err
	}
	var matches []string
	for _, v := range views {
		if strings.EqualFold(v.Name, ref) {
			matches = append(matches, v.ID)
		}
	}
	switch len(matches) {
	case 1:
		return matches[0], nil
	case 0:
		return "", fmt.Errorf("no view named %q\navailable views:\n%s", ref, formatBullets(viewNames(views)))
	default:
		return "", fmt.Errorf("ambiguous view name %q (%d matches)", ref, len(matches))
	}
}

// viewNames returns the sorted list of view names for candidate messages.
func viewNames(views models.ViewList) []string {
	names := make([]string, 0, len(views))
	for _, v := range views {
		names = append(names, v.Name)
	}
	sort.Strings(names)
	return names
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

// CreateView creates a view from a fully-resolved request (references already
// converted to UUIDs by [ViewService.BuildCreateRequest]) and returns it.
func (s *ViewService) CreateView(ctx context.Context, req models.ViewCreateRequest) (models.View, error) {
	r, err := s.client.NewRequest(ctx, "POST", api.ViewCreate, req)
	if err != nil {
		return models.View{}, err
	}
	return api.DoJSON[models.View](s.client, r)
}

// UpdateView applies a fully-resolved update (references already converted to
// UUIDs by [ViewService.BuildUpdateRequest]) to a view. The update is a full
// replacement of the view's items and metadata; plan_id is intentionally not
// sent, so a plan-backed view keeps its link.
func (s *ViewService) UpdateView(ctx context.Context, req models.ViewUpdateRequest) error {
	r, err := s.client.NewRequest(ctx, "POST", api.ViewUpdate, req)
	if err != nil {
		return err
	}
	_, err = api.DoJSON[bool](s.client, r)
	return err
}

// DeleteView deletes the view with the given UUID.
func (s *ViewService) DeleteView(ctx context.Context, viewID string) error {
	body := map[string]string{"viewId": viewID}
	r, err := s.client.NewRequest(ctx, "POST", api.ViewDelete, body)
	if err != nil {
		return err
	}
	_, err = api.DoJSON[bool](s.client, r)
	return err
}

// ---------------------------------------------------------------------------
// Reference resolution (items + widget filters)
// ---------------------------------------------------------------------------

// resolveItemRefs resolves a list of build_system_id references to the backend
// "type:uuid" item strings ("test:<uuid>", "group:<uuid>", "release:<uuid>").
// A reference matching nothing is reported as a warning and omitted so the rest
// of the view still builds; an ambiguous release name aborts.
func (s *ViewService) resolveItemRefs(ctx context.Context, refs []string) ([]string, []string, error) {
	var items []string
	var warnings []string
	for _, ref := range refs {
		id, kind, err := s.planner.ResolveGlobalRef(ctx, ref)
		if err != nil {
			if isNotFound(err) {
				warnings = append(warnings, fmt.Sprintf("item %q did not resolve to any release/group/test — omitted", ref))
				continue
			}
			return nil, warnings, err
		}
		items = append(items, string(kind)+":"+id)
	}
	return items, warnings, nil
}

// resolveFilterRefs resolves a widget filter (a list of build_system_id
// references) to bare entity UUIDs. As with items, an unresolved reference warns
// and is skipped.
func (s *ViewService) resolveFilterRefs(ctx context.Context, refs []string) ([]string, []string, error) {
	var ids []string
	var warnings []string
	for _, ref := range refs {
		id, _, err := s.planner.ResolveGlobalRef(ctx, ref)
		if err != nil {
			if isNotFound(err) {
				warnings = append(warnings, fmt.Sprintf("widget filter %q did not resolve to any release/group/test — omitted", ref))
				continue
			}
			return nil, warnings, err
		}
		ids = append(ids, id)
	}
	return ids, warnings, nil
}

// isNotFound reports whether err is (wraps) [ErrEntityNotFound] or is a
// release/user "no ... named" miss, all of which are treated as a warn-and-skip
// condition for view items.
func isNotFound(err error) bool {
	if err == nil {
		return false
	}
	if strings.Contains(err.Error(), ErrEntityNotFound.Error()) {
		return true
	}
	// ResolveReleaseID reports a missing release without wrapping the sentinel.
	return strings.HasPrefix(err.Error(), "no release named ")
}

// buildWidgetSettings fills in each widget type's default settings for any
// missing keys, resolves filter references to bare UUIDs, and reflows positions
// to a 1-based sequence — mirroring the dashboard editor — then returns the
// widget_settings JSON array string the backend stores. An empty widget list
// yields "[]" (the backend requires a non-empty string).
//
// An unrecognised widget type is not an error here: it is stored verbatim (no
// default settings are known) and reported as a warning, so a view built with a
// newer widget catalog than this CLI knows still round-trips through an update.
// User-supplied widget types (--widget / --file) are validated separately at the
// command boundary via [models.ValidateWidgetType].
func (s *ViewService) buildWidgetSettings(ctx context.Context, widgets []models.ViewWidget) (string, []string, error) {
	if len(widgets) == 0 {
		return "[]", nil, nil
	}
	var warnings []string
	out := make([]models.ViewWidget, 0, len(widgets))
	for i, w := range widgets {
		if models.IsKnownWidgetType(w.Type) {
			merged, err := fillWidgetDefaults(w.Type, w.Settings)
			if err != nil {
				return "", warnings, err
			}
			w.Settings = merged
		} else {
			warnings = append(warnings, fmt.Sprintf("widget type %q is not recognised by this CLI version — stored as-is", w.Type))
		}

		ids, warns, err := s.resolveFilterRefs(ctx, w.Filter)
		if err != nil {
			return "", warnings, err
		}
		warnings = append(warnings, warns...)
		w.Filter = nonNilSlice(ids)

		w.Position = i + 1
		out = append(out, w)
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return "", warnings, fmt.Errorf("encoding widget settings: %w", err)
	}
	return string(raw), warnings, nil
}

// fillWidgetDefaults merges the default settings for a widget type into the
// given settings JSON, adding only keys the caller omitted (existing values are
// preserved). A nil/empty settings object yields the type's full defaults. This
// matches the frontend's populateWidgetSettings behaviour.
func fillWidgetDefaults(widgetType string, settings json.RawMessage) (json.RawMessage, error) {
	current := map[string]any{}
	if len(settings) > 0 {
		if err := json.Unmarshal(settings, &current); err != nil {
			return nil, fmt.Errorf("parsing settings for widget %q: %w", widgetType, err)
		}
	}
	for k, v := range models.DefaultWidgetSettings(widgetType) {
		if _, ok := current[k]; !ok {
			current[k] = v
		}
	}
	raw, err := json.Marshal(current)
	if err != nil {
		return nil, fmt.Errorf("encoding settings for widget %q: %w", widgetType, err)
	}
	return raw, nil
}

// ---------------------------------------------------------------------------
// Create / update request building
// ---------------------------------------------------------------------------

// BuildCreateRequest turns a reference-based [models.ViewTemplate] into a
// fully UUID-resolved [models.ViewCreateRequest]. Unresolved items/filters are
// returned as warnings and omitted; an ambiguous release name aborts.
func (s *ViewService) BuildCreateRequest(ctx context.Context, tmpl models.ViewTemplate) (models.ViewCreateRequest, []string, error) {
	if strings.TrimSpace(tmpl.Name) == "" {
		return models.ViewCreateRequest{}, nil, fmt.Errorf("a view name is required (set 'name' in the file or pass --name)")
	}
	items, warnings, err := s.resolveItemRefs(ctx, tmpl.Items)
	if err != nil {
		return models.ViewCreateRequest{}, warnings, err
	}
	settings, wWarn, err := s.buildWidgetSettings(ctx, tmpl.Widgets)
	if err != nil {
		return models.ViewCreateRequest{}, warnings, err
	}
	warnings = append(warnings, wWarn...)

	return models.ViewCreateRequest{
		Name:        tmpl.Name,
		DisplayName: tmpl.DisplayName,
		Description: tmpl.Description,
		Items:       nonNilSlice(items),
		Settings:    settings,
	}, warnings, nil
}

// BuildUpdateRequest turns a reference-based [models.ViewTemplate] into the
// UUID-based [models.ViewUpdateRequest] for the given view UUID. The update is a
// full replacement: items and widget_settings are rebuilt from the template in
// their entirety, so a metadata-only edit must start from the current view (see
// the update command). plan_id is intentionally omitted to preserve it.
func (s *ViewService) BuildUpdateRequest(ctx context.Context, viewID string, tmpl models.ViewTemplate) (models.ViewUpdateRequest, []string, error) {
	if strings.TrimSpace(tmpl.Name) == "" {
		return models.ViewUpdateRequest{}, nil, fmt.Errorf("a view name is required")
	}
	items, warnings, err := s.resolveItemRefs(ctx, tmpl.Items)
	if err != nil {
		return models.ViewUpdateRequest{}, warnings, err
	}
	settings, wWarn, err := s.buildWidgetSettings(ctx, tmpl.Widgets)
	if err != nil {
		return models.ViewUpdateRequest{}, warnings, err
	}
	warnings = append(warnings, wWarn...)

	return models.ViewUpdateRequest{
		ViewID: viewID,
		UpdateData: models.ViewUpdateData{
			Name:           tmpl.Name,
			DisplayName:    tmpl.DisplayName,
			Description:    tmpl.Description,
			Items:          nonNilSlice(items),
			WidgetSettings: settings,
		},
	}, warnings, nil
}

// ---------------------------------------------------------------------------
// View → template transform (default get output / update base)
// ---------------------------------------------------------------------------

// ViewToTemplate converts a stored view into a reference-based
// [models.ViewTemplate] suitable for `view get` output and `view update --file`
// round-tripping. Membership is reverse-mapped via the view's resolve endpoint
// (whose items carry build_system_id / name); widget filter UUIDs are mapped
// back to references where possible. A filter UUID that cannot be mapped (e.g. a
// test inside a release/group item, not itself a standalone item) is kept as the
// raw UUID and reported as a warning.
func (s *ViewService) ViewToTemplate(ctx context.Context, view models.View) (models.ViewTemplate, []string, error) {
	resolved, err := s.getResolvedView(ctx, view.ID)
	if err != nil {
		return models.ViewTemplate{}, nil, err
	}

	// Reverse map: entity UUID → reference (build_system_id for tests/groups,
	// name for releases).
	refByID := make(map[string]string, len(resolved.Items))
	items := make([]string, 0, len(resolved.Items))
	for _, it := range resolved.Items {
		ref := itemRef(it)
		if ref == "" {
			continue
		}
		refByID[it.ID] = ref
		items = append(items, ref)
	}
	sort.Strings(items)

	widgets, warnings, err := s.widgetsToTemplate(view.WidgetSettings, refByID)
	if err != nil {
		return models.ViewTemplate{}, warnings, err
	}

	// Surface the plan link as its human-friendly key rather than a bare UUID.
	planKey, err := s.planner.PlanKeyByID(ctx, view.PlanID)
	if err != nil {
		return models.ViewTemplate{}, warnings, err
	}

	return models.ViewTemplate{
		ID:          view.ID,
		Name:        view.Name,
		DisplayName: view.DisplayName,
		Description: view.Description,
		PlanKey:     planKey,
		URL:         s.viewWebURL(view.Name),
		Items:       items,
		Widgets:     widgets,
	}, warnings, nil
}

// itemRef returns the reference form of a resolved item: build_system_id for
// tests and groups, name for releases. An empty result means the item cannot be
// referenced (skipped).
func itemRef(it models.ResolvedViewItem) string {
	switch it.Type {
	case "release":
		return it.Name
	default: // test, group
		return it.BuildSystemID
	}
}

// widgetsToTemplate parses a view's widget_settings JSON array and reverse-maps
// each widget's filter UUIDs to references via refByID. An unmapped UUID is kept
// verbatim and reported as a warning.
func (s *ViewService) widgetsToTemplate(widgetSettings string, refByID map[string]string) ([]models.ViewWidget, []string, error) {
	if strings.TrimSpace(widgetSettings) == "" {
		return nil, nil, nil
	}
	var stored []models.ViewWidget
	if err := json.Unmarshal([]byte(widgetSettings), &stored); err != nil {
		return nil, nil, fmt.Errorf("parsing widget_settings: %w", err)
	}
	var warnings []string
	out := make([]models.ViewWidget, 0, len(stored))
	for _, w := range stored {
		refs := make([]string, 0, len(w.Filter))
		for _, id := range w.Filter {
			if ref, ok := refByID[id]; ok {
				refs = append(refs, ref)
				continue
			}
			warnings = append(warnings, fmt.Sprintf("widget %q filter entity %q is not a view item — kept as UUID", w.Type, id))
			refs = append(refs, id)
		}
		w.Filter = refs
		out = append(out, w)
	}
	return out, warnings, nil
}

// ---------------------------------------------------------------------------
// Summaries (list output)
// ---------------------------------------------------------------------------

// BuildSummaries resolves a slice of views into per-view list summaries,
// reporting membership as an integer test count, the owner UUID as a username
// (falling back to the raw id when unknown), and the plan_id as its
// human-friendly plan key (falling back to the raw id for a stale link).
func (s *ViewService) BuildSummaries(ctx context.Context, views models.ViewList) ([]models.ViewSummary, error) {
	summaries := make([]models.ViewSummary, 0, len(views))
	for _, v := range views {
		owner, err := s.planner.UsernameByID(ctx, v.UserID)
		if err != nil {
			return nil, err
		}
		planKey, err := s.planner.PlanKeyByID(ctx, v.PlanID)
		if err != nil {
			return nil, err
		}
		summaries = append(summaries, models.ViewSummary{
			ID:          v.ID,
			Name:        v.Name,
			DisplayName: v.DisplayName,
			Description: v.Description,
			Owner:       owner,
			PlanKey:     planKey,
			Tests:       len(v.Tests),
			LastUpdated: v.LastUpdated,
			URL:         s.viewWebURL(v.Name),
		})
	}
	return summaries, nil
}
