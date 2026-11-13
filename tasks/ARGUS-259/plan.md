# ARGUS-259 — implementation plan

**Spec:** `tasks/ARGUS-259/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- All code is under `cli/`. Run `make fmt`, `make lint` and
  `go test -race ./...` in `cli/` before each commit.
- Tests use `testify` (`require`, `assert`) and `httptest` servers, as
  `internal/services/cloudflared_test.go` does. No test reaches GitHub.
- Errors are sentinel `var Err... = errors.New(...)` values wrapped with
  `%w`, as in `internal/services/cloudflared.go`.
- Every network call takes the `context.Context` of the caller and a
  timeout. The GitHub API base URL, the HTTP client, the clock, the
  executable path and the state directory are options of `Updater`, so the
  tests replace them.
- Commit subjects use `feature(cli/upgrade): ... [ARGUS-259]`.

## Task 1 — Release selection

**Files:**
- Create: `cli/internal/selfupdate/select.go`
- Test: `cli/internal/selfupdate/select_test.go`
- Modify: `cli/go.mod`, `cli/go.sum` (add `golang.org/x/mod`)

**Internals:** `Release` struct. `Select(current string, releases
[]Release, allowPrerelease bool) (Release, bool)`. `canonical(v string)
string` adds the `v` prefix that `semver` needs. `IsDev(v string) bool`
is true for `dev` and for any string that `semver.IsValid` rejects. A
candidate is a pre-release when its version has a pre-release part or when
`Release.Prerelease` is set. The core of a version drops its pre-release
and build parts.

- [x] Write table tests: stable to newer stable, stable skips a
      pre-release, stable with `allowPrerelease` takes a pre-release,
      `0.6.0-rc1` to `0.6.0-rc2`, `0.6.0-rc1` to `0.6.0`, `0.6.0-rc1` skips
      `0.7.0-rc1`, `0.6.0-rc1` with `allowPrerelease` takes `0.7.0-rc1`,
      nothing newer, empty list, invalid tags skipped, `0.6.0-rc1+build.1`
      to `0.6.0-rc2`, `0.6.0-rc.9` to `0.6.0-rc.10`, a release that GitHub
      marks as a pre-release skipped without `allowPrerelease`.
- [x] Run them and confirm the failure.
- [x] Write `Select` and `IsDev`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Release lookup on GitHub

**Files:**
- Create: `cli/internal/selfupdate/github.go`
- Test: `cli/internal/selfupdate/github_test.go`

**Internals:** `ListReleases(ctx, apiBase, client, goos, goarch) ([]Release, error)` calls
`GET {apiBase}/repos/scylladb/argus/releases?per_page=100&page=<n>`. It
reads the next page only while the pages before it hold no stable CLI
release for the platform, up to 5 pages. It sends `Authorization: Bearer` from `GITHUB_TOKEN`, else
`GH_TOKEN`, when one is set, and it sends a page again without the token
when GitHub answers 401. It keeps tags with the prefix `cli/v` that are not drafts. It sets
`ArchiveURL` from the asset `argus_<version>_<os>_<arch>.tar.gz`, where
`<os>` is `linux` or `macOS`, and `ChecksumURL` from
`argus_<version>_checksums.txt`. A release with no asset for this platform
is left out. A status other than 200 returns `ErrReleaseList`.
`ArchiveName(version, goos, goarch)` gives the archive name.

- [x] Write tests against `httptest`: backend tags and drafts are left out,
      the token header is sent when the variable is set, a 403 returns
      `ErrReleaseList`, a release with no asset for the platform is left
      out, a refused token is sent again without it, a page of backend
      releases leads to the next page, a page with only a CLI pre-release
      leads to the next page, the list stops after 5 pages.
- [x] Run them and confirm the failure.
- [x] Write `ListReleases` and `ArchiveName`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Download, verify and install

**Files:**
- Create: `cli/internal/selfupdate/install.go`
- Test: `cli/internal/selfupdate/install_test.go`,
  `cli/internal/selfupdate/export_test.go`

**Internals:** `Install(ctx, client, r Release, archiveName, target string)
error`. It reads the checksum file and finds the line for the archive name,
also in the binary-mode form `<sum> *<name>`. It streams the
archive through `sha256` and `gzip`/`tar`, and writes the `argus` entry to
`os.CreateTemp(filepath.Dir(target), ".argus-upgrade-*")`. A sum that does
not match returns `ErrChecksum`. An archive or a binary larger than 256 MiB
returns `ErrArchiveTooLarge`. It syncs the temporary file, copies the mode of
`target`, renames the temporary file over `target`, and removes it on every
error path.
`ExecutablePath() (string, error)` returns `os.Executable` through
`filepath.EvalSymlinks`.

- [x] Write tests: the binary at the target is replaced and keeps its mode,
      a wrong sum leaves the target unchanged and no temporary file, a
      missing checksum line returns `ErrChecksum`, an archive with no
      `argus` entry returns `ErrBinaryNotInArchive`, a read-only directory
      returns an error that `errors.Is` matches with `fs.ErrPermission`, a
      binary-mode checksum line matches, an oversized binary or archive
      returns `ErrArchiveTooLarge`.
- [x] Run them and confirm the failure.
- [x] Write `Install` and `ExecutablePath`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — Updater, daily state and lock

**Files:**
- Create: `cli/internal/selfupdate/updater.go`, `cli/internal/selfupdate/state.go`
- Test: `cli/internal/selfupdate/updater_test.go`

**Internals:** `Updater` with the options `WithAPIBase`, `WithHTTPClient`,
`WithPlatform`, `WithNow`, `WithExecutable`, `WithStateDir`. `New(current,
opts...)`.
The package reads the path and the file of the running binary when the
process starts. `WithExecutable` replaces both at `New`.
`Upgrade(ctx, allowPrerelease) (Result, error)` returns `ErrDevBuild` for a
`dev` build. Else it waits for a `flock` on the directory of the binary
until `ctx` ends, returns `ErrBinaryReplaced` when the path no longer holds
the file of the process start, then lists with a 30 s timeout and installs
with a 5 min timeout. Before the list it returns `ErrInstall` when
`access(2)` refuses to write to the directory. `Daily(ctx, stderr) (Result,
error)` returns at once when the effective user is root, does not own the
binary, or cannot write to its directory. Then it takes
`upgrade.lock` and the lock of the directory of the binary with
`syscall.Flock(LOCK_EX|LOCK_NB)`, and returns at once when another process
holds either, or when the binary was replaced. It reads `upgrade.json`,
returns when `last_check` is today in local time, writes today, then lists
with a 5 s timeout and installs with a 60 s timeout. On an install error it
writes one line `argus: cannot upgrade to <v>: <err>; run argus upgrade` to
`stderr`. It leaves out `; run argus upgrade` for a bad archive, and it
writes nothing when `ctx` ended. On success it writes `argus: upgraded
<from> -> <to>`. `Daily` writes nothing else.

- [x] Write tests: a second `Daily` on the same day sends no request, a
      `Daily` on the next day sends one, a failed list still writes the
      date, a held lock skips the check, a corrupt state file counts as no
      check, `Upgrade` on `dev` returns `ErrDevBuild`, an up-to-date binary
      gives `Upgraded: false` and no download, a replaced binary stops
      `Upgrade` and skips `Daily`, `Upgrade` waits for the directory lock
      and stops when `ctx` ends, a held directory lock skips `Daily`, a
      bad checksum warns without the hint, a canceled install warns
      nothing, root and a user that does not own the binary skip `Daily`,
      a read-only directory skips `Daily` and fails `Upgrade` before the
      list.
- [x] Run them and confirm the failure.
- [x] Write `Updater`, `Upgrade`, `Daily` and the state helpers.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Daily update and re-exec in `main`

**Files:**
- Create: `cli/cmd/autoupgrade.go`
- Modify: `cli/main.go`
- Test: `cli/cmd/autoupgrade_test.go`

**Internals:** `cmd.AutoUpgrade(ctx, args []string) (path string, ok
bool)`. It returns at once when the version is `dev`, when
`ARGUS_NO_AUTO_UPGRADE=1`, when `ARGUS_UPGRADED_FROM` is set, when an
argument is `-h`, `--help`, `__complete` or `__completeNoDesc`, or when
`rootCmd.Find` resolves the root, `upgrade`, `version`, `help` or
`completion`. It adds the default help and completion commands first, so
`Find` knows them. Otherwise it calls `Daily` with `config.CacheDir()` as
the state directory. `main` calls it before `ExecuteContext`, and exits
with 130 when a signal ended the context during the check. When it returns
`ok`, `main` calls `syscall.Exec(path, os.Args, append(os.Environ(),
"ARGUS_UPGRADED_FROM="+version))`. When `Exec` returns an error, `main`
writes one warning line and continues.

- [x] Write tests for the skip rules of `AutoUpgrade`, with an `Updater`
      that counts the calls.
- [x] Run them and confirm the failure.
- [x] Write `AutoUpgrade` and the change in `main`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 6 — `argus upgrade` command

**Files:**
- Create: `cli/cmd/upgrade.go`
- Test: `cli/cmd/upgrade_test.go`

**Internals:** `upgradeCmd` with `Use: "upgrade"`, the flag `--prerelease`,
the annotation `SkipAuthRetryAnnotation`, and a no-op `PersistentPreRunE`, as
`cli/cmd/version.go` has. It calls `Upgrade` and prints
`{"from","to","upgraded","path"}` as JSON, or the text line with `--text`.
An error returns exit code 1.

- [x] Write tests with a fake `upgrader` behind the `newUpgrader` factory:
      JSON output after an upgrade, the `--prerelease` flag, `upgraded: false` when up to date, the error on `dev`, the
      text output.
- [x] Run them and confirm the failure.
- [x] Write `upgradeCmd`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 7 — Documentation

**Files:**
- Modify: `cli/README.md`, section `Installation` and a new section
  `Updates`

- [ ] Describe the daily check, the `exec` of the new binary,
      `argus upgrade [--prerelease]`, the `dev` build rule, the pre-release
      rules, `ARGUS_NO_AUTO_UPGRADE`, `GITHUB_TOKEN`, and the state file.
- [ ] Run the verify sequence.
- [ ] Commit, with the boxes of this task checked.

## Task 8 — Release tag check

**Files:**
- Modify: `.github/workflows/cli-release.yml`, step `Resolve bare version`

- [ ] Refuse a pre-release identifier that mixes letters and digits, such
      as `rc1`, and name the `rc.N` form in the error.
- [ ] Commit, with the boxes of this task checked.

## Task 9 — User-Agent on Argus requests

**Files:**
- Modify: `cli/internal/api/api.go`, `cli/cmd/version.go`
- Test: `cli/internal/api/api_test.go`

**Internals:** `api.UserAgent(version) string` returns
`argus-cli/<version> (<os>/<arch>)`. `api.SetVersion(version)` sets the
header that `Client.NewRequest` puts on every request. `cmd.SetVersionInfo`
calls it, so `main` sets it before any request.

- [x] Write a test: a request through `Client.Do` carries the header with
      the version and the platform.
- [x] Run it and confirm the failure.
- [x] Write `UserAgent` and `SetVersion`.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.
