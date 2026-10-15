# ARGUS-238 — implementation plan

**Spec:** `tasks/ARGUS-238/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Ruff checks `argusAI/` and `scripts/` (it skips only `argus/`). Every import
  sits at the top of its module. The one exception is the existing lazy
  import in `argusAI/eval/harness.py`, kept for the optional extra.
- No comment or docstring that justifies the change. Fix only the text the
  change makes wrong.
- Tests mock the network with the `requests_mock` fixture (a dev
  dependency) and never download the model. The ONNX session and the
  tokenizer are fakes, so the suite needs no model on disk.
- Task 2 runs while chromadb is still installed. Task 3 removes it from the
  lock and from `.venv`.
- Verify sequence: `uv run pre-commit run --all-files`, `uv run pytest`
  (Docker), `yarn test`.
- Commits:
  - commitlint header (`refactor(argusAI): …`, `docs(tasks): …`)
  - a body of at least 30 characters
  - the last line is `Task: ARGUS-238`
  - no `Co-Authored-By` trailer
  - `git add` by explicit path only
- Leave the code uncommitted until Komachi reviews it.

## Task 1 — Run the embedder on onnxruntime, and add a local cosine

**Files:**
- Modify: `argusAI/utils/embedding.py`
- Modify: `argusAI/event_similarity_processor_v2.py` (the `cosine` import)
- Modify: `argusAI/eval/dedup.py` (the `cosine` import)
- Create: `argusAI/tests/test_embedding.py`

**Internals:**
- `EmbeddingModelError(Exception)`: raised when the model archive cannot be
  fetched or fails its SHA-256 check.
- `BgeSmallEnEmbeddingModel` keeps its six class attributes and docstring,
  and adds `MAX_TOKENS = 256`, `BATCH_SIZE = 32` and `DOWNLOAD_ATTEMPTS = 3`.
  - `__init__`: `_tokenizer` and `_session` start as `None`.
  - `__call__(texts)`: on the first call, `_load()`. Then it embeds `texts`
    in slices of `BATCH_SIZE` and returns one 1-D `float32` array per text.
    An empty list returns `[]`.
  - `_load()`: when `onnx/model.onnx` or `onnx/tokenizer.json` is missing,
    `_extract_archive()`. Then it builds the tokenizer (truncation and
    padding at 256, `[PAD]`/0) and the `InferenceSession` with the spec's
    `SessionOptions` and `providers=["CPUExecutionProvider"]`.
  - `_extract_archive()`: `_download()` unless the archive is on disk with
    the pinned SHA-256. Then `tarfile.extractall(DOWNLOAD_PATH, filter="data")`.
  - `_download(archive)`: creates `DOWNLOAD_PATH` and streams
    `MODEL_DOWNLOAD_URL` with `requests.get(stream=True, timeout=60)` and
    `raise_for_status()`. It retries a `requests.RequestException` or a
    SHA-256 mismatch, deleting the file each time: `DOWNLOAD_ATTEMPTS` tries
    with a 1 s, then 2 s sleep between them. Then it raises
    `EmbeddingModelError` from the last failure.
  - `_embed_batch(texts)`: `tokenizer.encode` per text, as chromadb does.
    The `input_ids` and `attention_mask` are int64, and `token_type_ids` is
    zeros. Pooling multiplies by the int64 mask (float64), clips the counts
    at 1e-9, normalizes with zero norms set to 1e-12, and casts to `float32`.
- `_sha256(path) -> str`: reads the file in 1 MiB chunks.
- `cosine(x, y) -> float`:
  `float(1.0 - np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-30))`.
- `EventEmbedder` is unchanged.

**Tests** (`argusAI/tests/test_embedding.py`). A fixture points
`DOWNLOAD_PATH` at `tmp_path` and patches `Tokenizer.from_file` and
`ort.InferenceSession` in `argusAI.utils.embedding` with small fakes: the
encodings carry `ids` and `attention_mask`, and the session returns a fixed
hidden-state array.
- `test_embeds_the_mean_of_attended_tokens_as_a_unit_vector`: padding rows
  are ignored, the norm is 1, the dtype is `float32`, and there is one
  vector per text.
- `test_embeds_a_zero_hidden_state_as_a_zero_vector`
- `test_returns_no_vectors_for_no_texts`
- `test_downloads_verifies_and_extracts_the_archive`: a tar.gz built in the
  test, served by `requests_mock`, with `_MODEL_SHA256` patched to its hash.
- `test_reuses_the_extracted_model_without_a_request`
- `test_extracts_a_cached_archive_without_a_request`
- `test_raises_after_three_mismatched_downloads_and_removes_the_file`
  (`time.sleep` patched)
- `test_retries_a_failed_request_then_succeeds`
- `test_cosine_is_zero_for_parallel_and_one_for_orthogonal_vectors`

- [x] Write the tests and run them against the current chromadb subclass.
      Confirm that they fail.
- [x] Rewrite `embedding.py`, and switch the two `cosine` imports.
- [x] Run `uv run pytest argusAI` and confirm that it passes.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Check parity with chromadb on real events

No repository file changes. Run while chromadb is installed. The script
lives in the scratchpad and is not committed.

- [x] Embed every `message` of `argusAI/eval/baseline/events.json` (27
      production events), raw and after `MessageSanitizer(write_log=False)`.
      Embed with the new `BgeSmallEnEmbeddingModel` and with a chromadb
      `ONNXMiniLM_L6_V2` subclass that carries the same six class
      attributes. Assert `np.array_equal` for every vector, and report the
      largest cosine distance (spec bound: below 1e-6).
- [x] Run `deduplicate_by_similarity` on the baseline events with the old
      code (`git stash`) and with the new code. Confirm the same canonical
      set and the same `repeats` counts.
- [x] Write the results on this box. onnxruntime 1.29.0, tokenizers 0.22.2:
      ```
      raw      : 27 messages, 27 bitwise equal, max cosine distance 0.00e+00
      sanitized: 27 messages, 27 bitwise equal, max cosine distance 0.00e+00
      dedup    : chromadb 16 canonical, onnxruntime 16 canonical, identical=True
      ```
      The old code ran in the same process, with the chromadb embedder and
      the chromadb `cosine` patched into `argusAI.eval.dedup`, in place of
      a `git stash`.

## Task 3 — Delete V1 and drop chromadb from the dependencies

**Files:**
- Delete: `argusAI/event_similarity_processor.py`
- Modify: `pyproject.toml` (`ai`, `ai-eval`: replace `chromadb >= 1.5.9`
  with `numpy >= 2.2`, `onnxruntime >= 1.23`, `tokenizers >= 0.22`)
- Modify: `uv.lock` (`uv lock`, no upgrade)
- Modify: `scripts/release/build-bundle.sh` (the self-check import line)
- Modify: `argusAI/README.md`: the overview sentence on V1, the "Same model
  family used by the legacy processor" bullet, the "Differences from V1"
  section, and the "Co‑existence with V1" section
- Modify: `docs/project/tech-stack.md` (the `ai` extra line)
- Modify: `argusAI/eval/config.example.yaml` (the "Needs the 'ai-eval'
  extra (chromadb)" comment)
- Modify: `argusAI/eval/harness.py` (the `noqa` reason names chromadb)

- [x] Delete V1, and edit the extras, the self-check and the text.
- [x] Run `uv lock`. Confirm that chromadb is gone, and that `onnxruntime`
      (1.29.0), `tokenizers` (0.22.2) and `numpy` keep their versions on
      Python 3.11 and newer. A floor of 1.24 failed for Python 3.10: no
      cp310 wheel. The floor is 1.23, and the 3.10 split takes 1.23.2.
- [x] Run `uv sync --all-extras`, and confirm that `import chromadb` fails
      and `import argusAI.event_similarity_processor_v2` works.
- [x] Run `git grep -i chroma`. Expect only the cache path in
      `argusAI/utils/embedding.py` and `argusAI/README.md`, plus `tasks/`
      and `docs/plans/archive/`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## After merge

- [ ] On the deploy, check that argus-prod runs `argus-ai-worker.service`
      and has no `argusai_event_similarity_processor.service`. The
      `argus_legacy_ai_units` list in `roles/argus` removes it.
