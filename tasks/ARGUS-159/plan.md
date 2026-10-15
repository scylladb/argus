# ARGUS-159 — implementation plan

**Spec:** `tasks/ARGUS-159/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- **Scope and verification.** The change lives under `cli/` only. Verify with
  `cd cli && make fmt && make lint && go test -race ./...`, then
  `uv run pre-commit run --all-files`. No backend or frontend code changes, so
  `uv run pytest` and `yarn test` have nothing to cover.
- **Comments.** Every exported Go symbol gets a doc comment, as the
  surrounding code does. No comment justifies the change. Fix a comment that
  the change makes wrong.
- **Tests.** Use `testify` (`assert`, `require`), `t.TempDir()`, and no Docker.
  A test that depends on Unix permissions lives in a `//go:build unix` file.
  The umask and cwd are process-wide, so a test that changes either does not
  call `t.Parallel`.
- **Errors.** No error is dropped where the user would care. A cleanup
  failure prints `warning: …` to stderr, and the command goes on. A best-effort
  cache write stays `_ = cache.Set(…)`, as everywhere else in the CLI.
- **Commits.**
  - Header: `fix(cli/cache): …` or `fix(cli/prometheus): …`.
  - Body: at least 30 characters.
  - Last line: `Task: ARGUS-159`.
  - No `Co-Authored-By` trailer.
  - `git add` by explicit path only.
- **Review.** Leave the code uncommitted until Komachi reviews it.

## Task 1 — Confine cache keys to the root and give each entry a directory

**Files:**
- Modify: `cli/internal/cache/cache.go`
- Modify: `cli/internal/cache/keys.go:220-226` (rewrite the `PrometheusLogKey`
  doc comment to say that the entry dir holds the archive)
- Create: `cli/internal/cache/cache_test.go`

**Internals:**
- `ErrInvalidKey = errors.New("cache: key leaves the cache root")` and
  `ErrDisabled = errors.New("cache: disabled")`, next to `ErrCacheMiss`.
- `New`: with an empty `baseDir`, keep `c.baseDir` empty instead of the
  relative `"cache"`.
- `Disabled()`: also true when `c.baseDir == ""`.
- `func (c *Cache) EntryDir(key string) (string, error)`:
  - `ErrDisabled` when `Disabled()`.
  - `fmt.Errorf("%w: %q", ErrInvalidKey, key)` unless
    `filepath.IsLocal(filepath.FromSlash(key))`.
  - Otherwise `filepath.Join(c.baseDir, filepath.FromSlash(key))`.
  - The doc comment states the contract: a file placed in the dir belongs to
    the entry.
- `Get`, `Set` and `Invalidate`: keep their `Disabled()` check first, then take
  the dir from `EntryDir` and return its error. `Get` returns it as is; every
  caller already treats an error as a miss.
- `Clear` and `Stats`: return early when `c == nil || c.baseDir == ""`.
- `Stats`: replace the `data.json`/`meta.json` loop with `os.ReadDir(entryDir)`
  and add up `Info().Size()` of each regular file.
- `removeEntry(dir string) error`, used by `PurgeExpired` (decided in the
  build): `RemoveAll` every child except `meta.json`, stopping at the first
  error, then `RemoveAll(dir)`. The doc comment of `PurgeExpired` stops calling
  the removal atomic.

**Tests** (`package cache`, matching `keys_test.go`):
- **Entry files:**
  - `TestEntryDir_HoldsTheFilesSetWrites`
  - `TestEntryDir_RefusesDisabledCache`
- **Files placed in an entry** (a `monitor-set-x.tar.zst` of 1000 bytes in a
  `PrometheusLogKey` entry):
  - `TestStats_CountsEveryFileInTheEntryDir`: the category bytes and
    `TotalBytes` equal the sum of the three files.
  - `TestPurgeExpired_RemovesFilesStoredInTheEntryDir`
  - `TestClear_RemovesFilesStoredInTheEntryDir`
- **Escaping keys:**
  - `TestKeysOutsideTheRootAreRefused`: a table of `../x`, `a/../../x` and an
    absolute path. A canary file one level above the cache root survives
    `Set` and `Invalidate`. `Get`, `Set` and `Invalidate` return
    `ErrInvalidKey`, and nothing outside the root is created.
- **Empty root:**
  - `TestEmptyRootTouchesNothing`: `t.Chdir(t.TempDir())`, create
    `./cache/x/file`, then call `New("")`'s `Clear`, `Stats`, `PurgeExpired`,
    `Set` and `Invalidate`. `./cache/x/file` survives.
- **`--no-cache` root:**
  - `TestClear_EmptiesADisabledCacheWithARoot`: `cache clear` under
    `--no-cache`.
- **Interrupted purge** (`cache_unix_test.go`, `//go:build unix`):
  - `TestPurgeExpired_KeepsMetaUntilTheEntryIsEmpty`: a 0500 subdirectory
    blocks the removal. `meta.json` survives the first purge, and the second
    purge finishes the entry once the mode is restored.

- [x] Write the failing tests.
- [x] Run `go test -race ./internal/cache/` and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Keep the cache root under `--no-cache`

**Files:**
- Modify: `cli/cmd/root.go:142-160`
- Test: `cli/cmd/root_test.go`

**Internals:**
- `func newCache(noCache bool, cacheTTL string, logger zerolog.Logger) *cache.Cache`
  takes the option building and the `--cache-ttl` warning out of
  `PersistentPreRunE`. It always passes `config.CacheDir()`.
- `PersistentPreRunE` calls it. It keeps the debug log and the `PurgeExpired`
  goroutine.

**Tests:**
- `TestNewCache_NoCacheKeepsTheCacheRoot`: `Dir()` is
  `filepath.Join(config.CacheDir(), "cache")` and `Disabled()` is true.

- [x] Write the failing test.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Refuse run IDs and archive names that leave their directory

**Files:**
- Modify: `cli/cmd/prometheus.go`
- Test: `cli/cmd/prometheus_test.go`

**Internals:**
- `func childPath(root, name string) (string, error)`:
  - Returns `filepath.Join(root, name)`.
  - Errors with `%q is not a single path element` unless
    `filepath.IsLocal(name)`, the dir of the joined path is `root`, and its base
    is `name`.
  - This rejects `""`, `.`, `..`, `../x`, `a/b`, `x/../y`, and Windows volume
    and device names.
- `func promDataRoot() string`: `filepath.Join(config.CacheDir(), "prometheus")`.
  It replaces the `os.UserCacheDir()` joins in `promDataDir`,
  `readRunIDFromDataDir` and `stopAllContainers`.
- `func promRunDir(root, runID string) (string, error)`: `childPath`, with the
  error wrapped as `invalid run ID: …`.
- `start` and `stop --run-id` call `promRunDir` before any docker or file
  system call.
- `start` builds the download path with `childPath(dataDir, monitorLog)`.

**Tests:**
- **Run IDs:**
  - `TestPromRunDir_ReturnsDirUnderRoot`
  - `TestPromRunDir_RejectsRunIDOutsideRoot`: a table of `""`, `.`, `..`,
    `../escape`, `../../..`, `nested/dir` and `x/../y`.
- **Archive names:**
  - `TestChildPath_RejectsServerNameWithPath`: `../x-monitor-set.tar.zst` and
    `sub/monitor-set.tar.zst`.

- [x] Write the failing tests.
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Run the container as the calling user

**Files:**
- Modify: `cli/cmd/prometheus.go`
- Delete: `cli/cmd/prometheus_config_test.go`
- Test: `cli/cmd/prometheus_test.go`

**Internals:**
- `func promDockerRunArgs(containerName, dataDir, configPath string, uid, gid int) []string`:
  - Today's argument list, plus `--user <uid>:<gid>` before `promImage`.
  - Leaves the flag out when `uid == -1`, with one comment: `os.Getuid` is -1
    on Windows.
  - `start` calls it with `os.Getuid()` and `os.Getgid()`.
- **Delete** `chmodRecursive` and its call, `promConfigMode`, and the
  `os.Chmod` in `writePromConfig`. `writePromConfig` becomes `os.WriteFile`
  with mode 0644 and a wrapped error.
- **Delete** `prometheus_config_test.go`: the umask tests and
  `TestChmodRecursive_KeepsModeUnderAnyUmask`. Move
  `TestWritePromConfig_WritesTheScrapeConfig` and
  `TestWritePromConfig_ReportsAFailedWrite` into `prometheus_test.go`.

**Tests:**
- `TestPromDockerRunArgs_RunsAsCallingUserBeforeImage`: `--user` is followed
  by `1000:1001` and comes before `promImage`.
- `TestPromDockerRunArgs_OmitsUserWhenUIDUnknown`

- [x] Write the failing tests.
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Keep the archive in its cache entry and the TSDB with its container

**Files:**
- Modify: `cli/cmd/prometheus.go`
- Modify: `cli/cmd/cache.go:13-23`: the `Long` help names
  `prometheus-logs/<run-id>/monitor-set-*.tar.zst`.
- Test: `cli/cmd/prometheus_test.go`
- Create: `cli/cmd/prometheus_unix_test.go` (`//go:build unix`)

**Internals:**
- **Delete** `promDataDir`, `cleanDataDir` and `writeRunIDFile`.
- `func removePromData(w io.Writer, dir string)`: `os.RemoveAll`. On error it
  prints `warning: could not remove prometheus data: <err>`.
- `func promContainerNames(ctx context.Context) ([]string, error)`: the
  `docker ps -a --filter name=argus-prom- --format {{.Names}}` call taken out
  of `promListCmd`. `list` uses it too.
- `func removeOrphanDataDirs(w io.Writer, root string, containers []string)`:
  - A missing root is silent; any other `ReadDir` error is a warning.
  - Skip a non-dir, and a dir whose `promContainerName(name)` is in
    `containers`.
  - Skip a dir that has no `run_id` file and whose `ModTime` is within
    `promMaxTTL`. One comment: such a dir belongs to a start that has not
    created its container yet.
  - Otherwise call `removePromData`.
- `func cachedArchivePath(c *cache.Cache, key string) string`:
  `cache.Get[string]`, then `c.EntryDir(key)`, then `childPath(dir, name)`, and
  the file must exist. On any failure it returns `""`.
- `func moveArchiveToCache(c *cache.Cache, key, archivePath string) error`:
  - `c.EntryDir(key)`. `ErrDisabled` returns nil.
  - Otherwise `cache.Set(c, key, filepath.Base(archivePath), "", cache.TTLPrometheusLog)`,
    then `os.Rename` into the entry dir.
- `func extractTarZstFile(path, dest string) error`: open, `extractTarZst`,
  close.
- **The `start` sequence**, in this order:
  1. `promRunDir`, then `checkDocker`.
  2. `pruneOldContainers`.
  3. `promContainerNames`, then `removeOrphanDataDirs`. A `docker ps` error
     prints a warning and the sweep is skipped.
  4. `containerExists` returns early.
  5. `os.MkdirAll(dataDir, 0o755)`, then a deferred `removePromData` unless
     `started`.
  6. `archivePath := cachedArchivePath(…)`. On a hit, `_ = cache.Set(…)`
     refreshes the TTL.
  7. On a miss, download into `childPath(dataDir, monitorLog)`.
  8. Extract the outer archive into the temp dir.
  9. On a download, `moveArchiveToCache`; a failure prints a warning.
  10. `findPromDataArchive`, extract it into `dataDir`, then
      `flattenSnapshotDir`.
  11. `writePromConfig`.
  12. `docker run promDockerRunArgs(…)`.
  13. `started = true`.
  14. Write `run_id`; a failure prints a warning.
  15. Get the port and print the address.

  The final `_ = cache.Set(…)` after `docker run` goes away.
- **`stop --run-id`:** `promRunDir`, `docker rm -f`, then `removePromData`.
- **`stopAllContainers`:** remove the containers as today. Then call
  `removePromData(stderr, promDataRoot())` in both branches, including "No
  argus prometheus containers found".

**Tests:**
- **Orphan sweep** (in `prometheus_test.go`):
  - `TestRemoveOrphanDataDirs_RemovesDirOfRemovedContainer`
  - `TestRemoveOrphanDataDirs_KeepsDirWithContainer`
  - `TestRemoveOrphanDataDirs_KeepsRecentDirOfStartInProgress`
  - `TestRemoveOrphanDataDirs_RemovesStaleDirOfAbortedStart`: `os.Chtimes` set
    two hours back, as the last step of the setup.
  - `TestRemoveOrphanDataDirs_IgnoresMissingRoot`: no warning.
- **Archive in the cache:**
  - `TestMoveArchiveToCache_PutsArchiveInCacheEntry`: the source is gone,
    `cachedArchivePath` returns the entry path, and the content is intact.
  - `TestMoveArchiveToCache_KeepsArchiveInPlaceWhenCacheDisabled`
  - `TestCachedArchivePath_MissesWhenEntryHasNoArchive`: an entry written by
    the old CLI holds only the name.
  - `TestCachedArchivePath_MissesOnTamperedName`: `data.json` holds
    `"../../x"`.
- **Unix permissions** (in `prometheus_unix_test.go`):
  - `TestRemovePromData_WarnsWhenFilesCannotBeRemoved`. Skip as root. Set
    `wal/` to 0500, and restore it in `t.Cleanup`. The warning names the file,
    and the dir is still there.

- [x] Write the failing tests.
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 6 — Check it on rootful Docker

With a build of the branch. The run used `XDG_CACHE_HOME` pointed at a scratch
root, seeded with a copy of the run's archive, and `ARGUS_DISABLE_CLOUDFLARE=1`,
so no step needed `sudo` or the Argus API. Komachi still runs
`sudo rm -rf ~/.cache/argus-cli/prometheus` once for the real cache.

- [x] Run `argus prometheus start --run-id 1e72eebe-a48d-4a3e-a560-c6ad0d85b1af`.
  `curl -s localhost:<port>/api/v1/label/__name__/values` lists the run's
  metrics: 1379 names, 598 of them Scylla. The container runs as `1000:1000`.
- [x] `find ~/.cache/argus-cli \( ! -user $USER -o -perm -o+w \)` prints
  nothing.
- [x] `stop --run-id …` removes `prometheus/<run>/` and keeps the archive in
  `cache/prometheus-logs/<run>/`. A second `start` prints no download.
- [x] `cache info` counts the archive under `prometheus-logs`, and `cache clear`
  removes it.
- [x] Set `expires_at` in that `meta.json` to the past, then run
  `argus cache info`. The entry and its archive are gone.
- [ ] Run `argus --no-cache prometheus start …` and then `stop`. Nothing is
  left behind. Only the failure path ran: without credentials, `start` failed
  at the API and removed its run dir. The download path needs Komachi's
  credentials.
- [ ] Ctrl-C during the download removes the run dir. Not run: it needs a
  download, so it needs Komachi's credentials.
- [x] `start --run-id ../..` and `stop --run-id ../..` fail with
  `invalid run ID`.
- [x] In a scratch dir that holds `./cache/x`, run `argus --no-cache cache clear`.
  `./cache/x` survives.

## Task 7 — Fix the review findings

**Files:**
- Modify: `cli/internal/cache/cache.go`, `cli/internal/cache/cache_test.go`
- Modify: `cli/cmd/prometheus.go`, `cli/cmd/prometheus_test.go`
- Create: `cli/cmd/prometheus_cmd_unix_test.go` (`//go:build unix`)

**Internals:**
- `EntryDir` also refuses a key that cleans to `.`, which is the cache root.
- `claimRunDir(dir string) error`: `MkdirAll` the parent, then `os.Mkdir`.
  `fs.ErrExist` turns into an error that names the dir and says to remove it.
  `start` calls it in place of `MkdirAll`, before it sets up the deferred
  cleanup.
- `removeOrphanDataDirs(w, root, listContainers func() ([]string, error))`:
  scans for candidates first, then lists the containers. It skips the list
  when there are no candidates. A list error prints
  `warning: skipping prometheus data cleanup`.
- `moveArchiveToCache` becomes `cacheArchive`. It removes the archive when
  the cache is disabled, as the spec's `--no-cache` constraint states.

**Tests:**
- **Cache keys:** `TestKeysOutsideTheRootAreRefused` adds `.` and `a/..`.
- **Orphan sweep:**
  - `TestRemoveOrphanDataDirs_KeepsDirWhoseContainerStartsDuringTheSweep`
  - `TestRemoveOrphanDataDirs_WarnsWhenContainersCannotBeListed`
- **Run dir and archive:**
  - `TestClaimRunDir_CreatesTheDir`
  - `TestClaimRunDir_RefusesAnExistingDir`
  - `TestCacheArchive_PutsArchiveInCacheEntry`
  - `TestCacheArchive_DropsArchiveWhenCacheDisabled`
- **Command level**, run against a fake `docker` on `PATH` and an
  `XDG_CACHE_HOME` under `t.TempDir()`. The helper checks that
  `config.CacheDir()` sits there before anything runs:
  - `TestPromStart_ReusesTheCachedArchive`
  - `TestPromStart_FailedRunLeavesNoRunDir`
  - `TestPromStart_RefusesARunDirThatAlreadyExists`
  - `TestPromStop_RemovesTheRunDirAndKeepsTheArchive`

- [x] Write the failing tests.
- [x] Run them and confirm the failures.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] On rootful Docker with a scratch `XDG_CACHE_HOME`, two parallel starts
  of one run: one runs Prometheus, the other fails with `already exists`, and
  the running one keeps its data.
- [x] A leftover run dir that the sweep cannot empty: the sweep warns, and
  `start` refuses with the dir to remove.
- [x] Commit, with the boxes of this task checked.
