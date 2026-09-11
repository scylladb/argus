## Coding Style

### Python Target
Python code targets 3.12. CI pins 3.12 in every workflow. `pyproject.toml`
declares `requires-python = ">=3.10"` and Ruff sets `target-version = "py310"`,
so a 3.11 or 3.12 syntax feature reads as an error to the linter.

### Formatting
4-space indentation and a 120-character line width. `ruff format` applies both.
`pyproject.toml` sets `line-length = 120` and ignores `E501`.

### Ruff Reach
`pyproject.toml` sets `exclude = ["argus/"]` with `force-exclude = true`. Ruff
therefore checks the scripts, the AI workers and the root modules, and skips the
whole `argus/` package. A change under `argus/` passes the hook without a lint
pass, so read it with more care.

The rule set is explicit: `lint.select` names the rules, `lint.preview = true`
and `lint.explicit-preview-rules = true` enable the named preview rules only.
Add a rule to `lint.select` rather than a blanket rule family.

### Pre-commit Hooks
`pre-commit` runs `ruff format` and `ruff check --fix --preview` on staged
Python files, plus trailing whitespace, end-of-file, YAML, JSON, large-file and
private-key checks. Install the hooks with `uv run pre-commit install`.

ESLint, Prettier and svelte-check are installed. No hook and no workflow runs
them. Run them by hand when you touch the frontend.

### Python Naming
- Files: snake_case (`results_service.py`, `testrun_api.py`)
- Functions and methods: snake_case
- Private functions: underscore prefix
- Classes: PascalCase (`PlanningService`, `ArgusGenericResultMetadata`)
- Constants: UPPER_CASE

### Frontend Naming
One directory per feature area under `frontend/`, in PascalCase, with the main
component named after the directory. `Stores/` holds shared state. `Common/`
holds helpers and type definitions.

### Descriptive Names
Choose names that communicate intent. Avoid an abbreviation or a single letter
outside a tight loop.

### Focused Functions
Write a function that does one thing. A small function is easier to read, to
test and to change.

### No Dead Code
Remove an unused import, a commented-out block and an orphaned function in the
same change. A reviewer flags each one.

### No Backward Compatibility Unless Required
Write no extra code path for backward compatibility without a stated need. A
reviewer flags a compatibility shim for removal in the same pull request.

### DRY (Don't Repeat Yourself)
Extract repeated logic into a function or a module.
