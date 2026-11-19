# ARGUS-259 — Users keep running old versions of the argus CLI

## Problem

The argus CLI never checks for a newer version. A user installs a binary from
the releases page, puts it on `$PATH`, and runs it until they replace it by
hand. Nothing tells the user that a newer release exists.

Argus sometimes changes an endpoint in a way that an older CLI cannot read.
The user with the old CLI then gets a failure. They must find the cause and
reinstall by hand. Users also miss the fixes and the features of each new
release.

The `scylladb/argus` releases page holds two release streams. The CLI
releases have tags like `cli/v0.5.0`. The backend releases have tags like
`v0.16.7`. The release that GitHub marks as `Latest` can be from either
stream.

## Who it affects

- Engineers who run the argus CLI on their workstations, on Linux and macOS.
- Automation that runs the argus CLI in CI, where nobody reads a notice.
- AI agents (Zeus, Maia) that call the argus CLI through the `argus` skill.
- Argus maintainers, who cannot change an endpoint without breaking old CLI
  versions in the field.

## Evidence

Jira issue ARGUS-259:

```
Users keep running old argus CLI versions. Argus sometimes breaks compatibility with older CLI versions, and then those users get failures. Users also miss bugfixes and new features because nothing tells them that a newer version exists.
```

```
The update applies in every environment, CI included.
The update never fails or repeats a request that already succeeded.
The CLI does not query the releases page on every command.
```

`cli/README.md`, section `Installation`:

```
Download the latest release from the [releases page](https://github.com/scylladb/argus/releases) and place the binary somewhere on your `$PATH`.
```

`gh release list --repo scylladb/argus --limit 5` on 2026-11-12:

```
cli/v0.5.0	Latest	cli/v0.5.0	2026-11-10T14:46:51Z
v0.16.7		v0.16.7	2026-10-26T12:29:46Z
v0.16.6		v0.16.6	2026-10-26T11:41:33Z
cli/v0.4.0		cli/v0.4.0	2026-10-26T09:54:12Z
cli/v0.3.1		cli/v0.3.1	2026-10-08T07:04:25Z
```

The user who requested the task, on how the update runs:

```
automatically upgrade the version on the first run once a day, first time that it's run
with hot binary swap
```

```
also add a special command --upgrade to do the upgrade of the argus-cli, but also on the first run once a day, we use the semantic versioning
```

```
dev builds are special kind so do not run the upgrade on the dev build, for pre-releases, only in --upgrade --prerelease
```

```
if on prerelease you can update to the same version next prerelease or to the stable one
```

## What good looks like

- A user with an older CLI runs any command. Afterwards the installed binary
  is the latest CLI release, with no manual step.
- The CLI checks for a new release on the first command of a day only. The
  other commands of that day send no request to the releases page.
- The CLI replaces its own binary on disk while the command runs. The
  command that started the update completes with its normal result.
- A user runs `argus --upgrade` and gets the latest release at once, at any
  time of the day.
- The CLI compares versions by semantic versioning. It installs a release
  only when that release is newer than the running binary.
- A `dev` build never updates itself, from the daily check or from
  `--upgrade`.
- On a stable build, the daily check and `argus --upgrade` install stable
  releases only. `argus --upgrade --prerelease` also considers pre-releases.
- On a pre-release build, such as `v0.6.0-rc1`, the daily check and
  `argus --upgrade` install a newer pre-release of the same version, such as
  `v0.6.0-rc2`, or a newer stable release, such as `v0.6.0`.
- A CLI that is already on the latest release does not change.
- A failed check or a failed download does not fail the command of the user.
- The update works on Linux and macOS, on amd64 and arm64, and in CI.
- The CLI documentation describes the update behavior.

## Out of scope

- Windows builds. The release matrix ships none.
- A change to the backend release stream or to its tags.
- Installers from package managers, such as Homebrew or apt.
- An Argus endpoint that tells the CLI the minimum version it supports.
