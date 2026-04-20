# Plan Anti-Patterns Catalog

Common mistakes when writing Argus implementation plans. Each entry includes the symptom, why it's wrong, and a fix.

---

## Content Anti-Patterns

### PAP-1: Too Much Code in the Plan

**Symptom:** The plan includes full implementation code — complete functions, classes, or modules — instead of describing what to build.

**Why it's wrong:** A plan is a roadmap, not a codebase. Embedding full implementations makes the plan brittle (code changes invalidate the plan), hard to review (reviewers must read code instead of design), and misleading (the code may not compile or handle edge cases). The actual implementation belongs in PRs.

**Fix:** Use short code snippets (5-15 lines) only to illustrate interfaces, configuration formats, or API contracts. Describe behavior in prose; let the implementation phase produce the real code.

**Before:**

````markdown
### Phase 2: Implement Caching Layer

```python
class ResultCache:
    def __init__(self, ttl=300):
        self.ttl = ttl
        self._cache = {}
        self._timestamps = {}

    def get(self, key):
        if key in self._cache:
            if time.time() - self._timestamps[key] < self.ttl:
                return self._cache[key]
            del self._cache[key]
        return None

    def set(self, key, value):
        self._cache[key] = value
        self._timestamps[key] = time.time()
        # ... 30 more lines
```
````

````

**After:**
```markdown
### Phase 2: Implement Caching Layer

**Description**: Add TTL-based in-memory cache for release dashboard queries
to reduce ScyllaDB load on frequently accessed data.

**Key design decisions**:
- Simple dict-based cache with TTL expiration (not Redis — single-process deployment)
- 300-second default TTL, configurable per endpoint
- Cache invalidation on write operations

**Interface**:
```python
cache = ResultCache(ttl=300)
cached = cache.get("release:uuid")  # Returns None on miss/expiry
cache.set("release:uuid", data)
````

````

---

### PAP-2: Missing Diagrams for Complex Interactions

**Symptom:** The plan describes a complex multi-component interaction (cross-service communication, state machines, multi-layer data flows) using only prose, without any visual representation.

**Why it's wrong:** Prose alone cannot convey component relationships, data flows, or state transitions clearly. Readers (human and AI) miss dependencies, race conditions, or circular references that a diagram makes obvious.

**Fix:** Add ASCII diagrams or Mermaid diagrams for any interaction involving 3+ components, state transitions, or data flows across system boundaries.

**Before:**
```markdown
The client sends test results to the backend API which stores them in
ScyllaDB. The frontend polls the API for updated results and renders
them on the dashboard. The CLI tool also queries the API for status.
````

**After:**

    Client (argus-client)
        └── POST /api/v1/results ──► Backend (Flask)
                                        ├── store ──► ScyllaDB
                                        └── serve ──► GET /api/v1/results
                                                        ├── ◄── Frontend (Svelte)
                                                        └── ◄── CLI (argus-cli)

**When to use diagrams**:

- 3+ components interacting
- State machines or lifecycle transitions
- Data flows across system boundaries (e.g., client → backend → database → frontend)
- Request/response sequences involving multiple services

---

### PAP-3: Overly Granular Phases

**Symptom:** Phases include implementation-level details — specific function signatures, line-by-line changes, exact variable names — instead of design-level deliverables.

**Why it's wrong:** Over-specifying in the plan constrains the implementer unnecessarily, becomes stale as soon as the code evolves, buries the design intent under implementation noise, and makes the plan unreadable for stakeholders who need the "what" and "why", not the "how".

**Fix:** Phases should describe deliverables and design decisions, not line-by-line implementation. Leave the "how" for the PR.

**Before:**

```markdown
### Phase 1: Add New API Endpoint

1. Open `argus/backend/controller/api.py`
2. Add route after line 342:
   `@bp.route("/api/v1/releases/<release_id>/summary", methods=["GET"])`
3. Add function `def get_release_summary(release_id):`
4. Import `ReleaseSummaryService` on line 15
5. Run `uv run ruff check` to fix formatting
```

**After:**

```markdown
### Phase 1: Add Release Summary Endpoint

**Description**: Add `GET /api/v1/releases/<release_id>/summary` endpoint
returning aggregated test results per release.

**Deliverables**:

- New route in `argus/backend/controller/api.py`
- Service method in `argus/backend/service/results_service.py`
- Response schema matching existing patterns

**Definition of Done**:

- [ ] Endpoint returns JSON with release summary data
- [ ] Integration test covers happy path and 404 case
- [ ] `uv run ruff check` passes
```

---

### PAP-4: Vague or Unmeasurable Goals

**Symptom:** Goals use words like "improve", "better", "optimize", "enhance" without concrete criteria for what success looks like.

**Why it's wrong:** Vague goals cannot be validated. There is no way to know when the work is done. Different reviewers will have different interpretations of "improve performance." The plan has no accountability.

**Fix:** Every goal must have a measurable criterion or a verifiable condition. If a metric is unknown, state the target condition explicitly.

**Before:**

```markdown
## Goals

1. Improve API performance
2. Make the dashboard more responsive
3. Better error handling
4. Optimize database queries
```

**After:**

```markdown
## Goals

1. **Reduce dashboard load time to under 2s** for releases with 500+ test runs
2. **Eliminate N+1 queries** in release summary endpoint (currently 1 query per test run)
3. **Return structured error responses** with error codes for all 4xx/5xx responses
4. **Add query-level caching** with 5-minute TTL for read-heavy endpoints
```

---

### PAP-5: Conflicting or Contradictory Requirements

**Symptom:** Different sections of the plan state incompatible goals, design decisions, or constraints.

**Why it's wrong:** Conflicting requirements cause implementation deadlocks — the implementer cannot satisfy both constraints and must guess which one the plan author actually intended. This leads to rework, incorrect implementations, or abandoned phases.

**Fix:** Before finalizing, cross-check the plan for consistency:

- Do all phases support the stated goals?
- Does the risk mitigation section address risks that the implementation creates?
- Are assumptions in one section contradicted by constraints in another?
- If tradeoffs exist, state them explicitly with a chosen resolution.

---

## Structure Anti-Patterns

### PAP-6: Missing "Current State" Code References

**Symptom:** The Current State section describes how things work in general terms without pointing to specific files, classes, or methods.

**Why it's wrong:** Without code references, reviewers cannot verify the analysis is accurate. The implementer may look at the wrong code. The plan may describe outdated behavior.

**Fix:** Every claim about current behavior must cite a specific file path and optionally a class or method. Verify each reference exists using file-reading tools.

**Before:**

```markdown
## Current State

The backend handles test results through a service layer. Results are
stored in the database and served via REST endpoints. The frontend
displays them on the dashboard.
```

**After:**

```markdown
## Current State

- `argus/backend/service/results_service.py:ResultsService` — CRUD operations for test results
- `argus/backend/controller/api.py` — REST endpoints, routes defined with Flask blueprints
- `argus/backend/db/testrun.py:SCTTestRun` — CQLEngine model for test run data
- `frontend/WorkArea/TestRunPage.svelte` — Displays individual test run results
```

---

### PAP-7: Phases Without Definition of Done

**Symptom:** Phases describe what to build but have no checkboxes or verifiable criteria for completion.

**Why it's wrong:** Without Definition of Done, there is no agreed boundary for "this phase is complete." PRs may be merged with partial work, or reviewers may block PRs that are actually complete but lack documented criteria.

**Fix:** Every phase needs a `**Definition of Done**:` section with checkbox items (`- [ ] criterion`). Each criterion should be something a reviewer can verify.

**Before:**

```markdown
### Phase 3: Add Integration Tests

Write integration tests for the release API endpoints. Cover all
the important scenarios and edge cases.
```

**After:**

```markdown
### Phase 3: Add Integration Tests

**Importance**: Critical
**Description**: Add httpx-based integration tests for release API
endpoints, exercising real ScyllaDB via Docker.

**Definition of Done**:

- [ ] Tests cover GET, POST, PUT, DELETE for release endpoints
- [ ] Tests assert on JSON response structure, not ORM objects
- [ ] Tests run against Docker ScyllaDB instance
- [ ] `uv run pytest argus/backend/tests/ -v` passes
```

---

### PAP-8: Monolithic Phase Spanning Multiple PRs

**Symptom:** A single phase contains too many deliverables to fit in one Pull Request — refactoring + new feature + tests + configuration + documentation all in one phase.

**Why it's wrong:** Large PRs are hard to review, slow to merge, and risky to revert. They also create merge conflicts with other ongoing work.

**Fix:** Split into smaller phases, each scoped to a single PR targeting ≤200 lines of code. Use dependencies to maintain order. A good phase produces 1-3 related deliverables.

---

## Quick Reference

| ID    | Anti-Pattern                              | One-Line Fix                                                       |
| ----- | ----------------------------------------- | ------------------------------------------------------------------ |
| PAP-1 | Too much code in the plan                 | Use short snippets for interfaces only; describe behavior in prose |
| PAP-2 | Missing diagrams for complex interactions | Add ASCII/Mermaid diagrams for 3+ component interactions           |
| PAP-3 | Overly granular phases                    | Describe deliverables, not line-by-line changes                    |
| PAP-4 | Vague or unmeasurable goals               | Add measurable criteria or verifiable conditions                   |
| PAP-5 | Conflicting requirements                  | Cross-check goals, phases, and risks for consistency               |
| PAP-6 | Missing code references in Current State  | Cite specific file paths, verify they exist                        |
| PAP-7 | Phases without Definition of Done         | Add checkbox criteria to every phase                               |
| PAP-8 | Monolithic phase spanning multiple PRs    | Split into single-PR-scoped phases                                 |
