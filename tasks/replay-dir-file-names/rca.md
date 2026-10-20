# replay-dir-file-names — `argus run replay --dir` finds no replay log of an SCT run

**Date**: 2026-10-20

## Root cause

The CLI and the Python client use two different file name formats.

`ReplayFileNamePattern` in `cli/internal/replay/extract.go:19` accepts only
`argus_replay_log_<run>_<ts>.jsonl`, with an optional `.zst` or `.zstd`:

```go
`^argus_replay_log_(?P<run>[^/]+?)_(?P<ts>\d+)\.jsonl(?:\.zstd?)?$`
```

`ReplayLog.__init__` in `argus/client/replay_log.py:101` writes a pid and a
uuid4 hex after the timestamp:

```python
suffix = f"{_now_ns()}_{os.getpid()}_{uuid.uuid4().hex}"
self._path: Path = log_dir_path / f"argus_replay_log_{safe_run_id}_{suffix}.jsonl"
```

Commit `08944943` (2026-07-20, `fix(client): forward run_id into
ArgusGenericClient, uuid-harden replay log filenames`) added the pid and the
hex. The pattern dates from commit `2c86dcfb` (2026-05-27) and did not change
with it. After `<ts>` the pattern expects `.jsonl`, finds `_<pid>`, and fails.

Two callers use the pattern:

1. `collectFiles` in `cli/cmd/replay.go:217` skips each directory entry that
   does not match. Every SCT log is skipped, so `--dir` returns the error in
   `intent.md`.
2. `matchesRunID` in `cli/internal/replay/extract.go:81` keeps a file that
   does not match, so `--run-id` keeps every log of a `.jsonl.zst` file and
   filters nothing.

`--file` works, because it does not use the pattern for a plain `.jsonl`.

## Approaches

1. **Selected.** Accept the pid and the hex as an optional part of the
   pattern: `_(?P<ts>\d+)(?:_\d+_[0-9a-f]{32})?\.jsonl`. Both formats match,
   and the groups `run` and `ts` keep their meaning. The change is one line
   in the CLI. Old logs and new logs both replay.
2. Match the prefix and the suffix only, as the `.tar.zst` path does, and read
   the run ID from the records. This drops the `run` group, so `--run-id`
   must open every file. It costs more code and more I/O for the same result.
3. Change the Python client back to `<run>_<ts>`. This brings back the name
   collisions that commit `08944943` fixed on a shared log directory, and
   logs that SCT already wrote keep the new format.

Approach 1 is the smallest change that accepts every log that exists.

## Regression test

- `TestReplayFileNamePatternMatchesPythonClientNames` in
  `cli/internal/replay/extract_test.go`: the pattern matches the old name and
  the Python client name, with and without `.zst`, and returns the run ID and
  the timestamp.
- `TestCollectFiles_FindsPythonClientNamesByRunID` in
  `cli/cmd/replay_upload_test.go`: `collectFiles` finds two Python client
  logs in a directory, and `--run-id` keeps one of them.

Both tests fail before the fix and pass after it.

## Risks

| Risk | Response |
|---|---|
| A run ID that ends in `_<digits>_<32 hex>` splits in the wrong place | Run IDs are UUIDs. The client strips path characters and keeps at most 64 characters. A UUID has no `_`. |
| The client changes the name format again | The test holds the client format verbatim, so a change shows up in review of the CLI. |
