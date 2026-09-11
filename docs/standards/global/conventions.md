## Development Conventions

### Predictable Structure
Keep a file in the layer that owns it. A route goes to
`argus/backend/controller/`, the logic to `argus/backend/service/`, the data
model to `argus/backend/models/`. A new test source goes to
`argus/backend/plugins/<name>/`.

### Up-to-Date Documentation
Update `AGENTS.md` when the module map or the tooling changes. Update
`docs/project/architecture.md` when a layer, a plugin or a deployable part
changes. Update `docs/INDEX.md` when you add or remove a document.

### Commit Messages
`commitlint` runs at the `commit-msg` stage and enforces the format. A
`pre-commit run --all-files` pass does not cover it.

- Header: at most 72 characters.
- Type: one of `ci`, `docs`, `feature`, `fix`, `improvement`, `perf`,
  `refactor`, `revert`, `style`, `test`, `unit-test`.
- Scope: required, at least 5 characters.
- Subject: 10 to 85 characters, no full stop at the end.
- Body: required, at least 30 characters, a blank line before it, and at most
  100 characters per line.

### Pull Requests
Title a pull request `type(scope): summary`. Describe the intent and the manual
validation steps. Add a screenshot for a UI change and a payload snippet for an
API change. End the body with `Fixes ARGUS-<n>`.

Compose a commit around one logical change. Run the verify sequence in
`CLAUDE.md` before you push.

### AI-Assisted Transparency
A workflow adds the `ai-assisted` label when it finds an AI marker in the pull
request body or in a commit trailer. Keep the marker in place.

### Pinned GitHub Actions
Every workflow pins a third-party action to a full commit SHA with a `# vX.Y.Z`
comment. Keep new entries in that form.

### Committed Lockfiles
All three ecosystems commit a lockfile: `uv.lock`, `yarn.lock` and
`cli/go.sum`. A dependency change updates the lockfile in the same commit.

### uv for All Python Tooling
uv is the only Python tool runner. `uv sync --all-extras` for setup, and
`uv run <cmd>` for everything else.

### Secrets and Configuration
`argus.local.yaml` and `argus_web.yaml` hold the local configuration, and
`.gitignore` excludes both. Copy `argus_web.example.yaml` to start. Never commit
a secret. Use the Docker Compose setup in `dev-db/` for a local database, and
stop it after use.

Keep a sample data archive outside the repository. A production artifact must
not reach a commit.

### Minimal Dependencies
Keep the dependency list short. State why a major dependency arrives.

### Consistent Reviews
`docs/standards/REVIEW.md` holds the review policy. It applies to every pull
request.

### Non-Blocking Review Feedback
Merge working code. Track the remaining comments as a follow-up Jira issue and
link it in the pull request thread.

### Testing Standards
`docs/standards/testing/test-writing.md` states the required depth. A new code
path arrives with a test.

### Feature Flags
Use a flag for an incomplete feature. A long-lived branch drifts.

### Build What Is Needed
Write no speculative code. See `minimal-implementation.md`.
