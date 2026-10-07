# Argus CLI

Command-line interface for [Argus](https://argus.scylladb.com) — a test tracking system for automated pipelines. Use it to inspect test runs, fetch logs, stream activity, submit comments, and manage SSH tunnels into Argus clusters.

## Installation

Download the latest release from the [releases page](https://github.com/scylladb/argus/releases) and place the binary somewhere on your `$PATH`.

For a quick install example, see the [root README](../README.md).

### From source

Requires Go 1.25+.

```bash
git clone https://github.com/scylladb/argus
cd argus/cli
go build -o argus .
```

## Common Flows

Most users only need one of these:

### Production Argus with browser login

Use this on a developer machine when connecting to `argus.scylladb.com` or another Argus instance protected by Cloudflare Access.

```bash
argus auth
```

### CI, automation, or servers

Use environment variables instead of keychain-based auth:

```bash
export ARGUS_CF_ACCESS_CLIENT_ID=your-client-id
export ARGUS_CF_ACCESS_CLIENT_SECRET=your-client-secret
export ARGUS_AUTH_TOKEN=your-pat
```

### Local or non-Cloudflare Argus

Use a direct token against a local or internal deployment:

```bash
argus auth-token <your-token>
```

### After auth

Check the current CLI configuration:

```bash
argus config list
```

## Replaying a run

An SCT run writes each Argus call it makes to a replay log
(`argus_replay_log_<run_id>_<ts>.jsonl`). `argus run replay` sends these logs
to Argus, and the server applies the calls again. Use it to put a local or
minicloud run into a shared Argus, or to recover a run after an outage.

Replay the logs of one run from an SCT results directory:

```bash
argus run replay --dir ~/sct-results/latest --run-id <run_id>
```

Replay an archive or single files:

```bash
argus run replay --file argus-replay-baseline.tar.zst
argus run replay --file argus_replay_log_<run_id>_<ts>.jsonl.zst
```

### Where a local run goes

A local or minicloud run has no Jenkins job. When the logs hold one such
run, the replay files it under your user by default:

```
local-runs/<your Argus username>/<job>
```

`<job>` is the name of the first SCT config file of the run. For example,
`test-cases/longevity/longevity-100gb-4h.yaml` gives
`local-runs/jdoe/longevity-100gb-4h`. Each replay of the same test adds the
next build: `#1`, `#2`, and so on. To find your local runs in Argus, open the
`local-runs` release and then the group with your username, or search for
`local-runs/<your username>`.

The replay creates the release, the group and the test when they do not
exist. It also gives the run a new run ID, makes you its starter and
assignee, and records the original run, as for `--build-id` below. A Jenkins
run keeps its recorded job path and run ID, so a replay after an outage
restores the original run.

To replay a local run as recorded, with its original run ID, give
`--keep-run`. Use it to finish a local run that reached Argus only in part.

### Replay into your own build path

To put the runs under a build path of your choice, give `--build-id`. It
works for local and Jenkins runs, and it replaces the `local-runs` default:

```bash
argus run replay --file argus-replay-baseline.tar.zst \
  --build-id scylla-staging/jdoe/my-argus-local-run
```

The path has two or more names. The first name is the release, the last
name is the test and the job name, and the names between them make the
group. The release must exist in Argus. Only the `local-runs` default creates
its release. The CLI checks the form of the path before it uploads the logs.

Each run under the path gets a build number, like a build of a Jenkins job.
The first replay into a path is `#1`, the next one is `#2`, and so on. To
choose the number, end the path with `#<n>`:

```bash
argus run replay --file argus-replay-baseline.tar.zst \
  --build-id scylla-staging/jdoe/my-argus-local-run#10
```

The number must be free under the path. A number that a failed replay
reserved, and that no run holds, becomes free again after ten minutes. When the logs hold more than one
run, the runs take `n`, `n+1`, and so on.

With `--build-id`, the replay:

1. Gives each run in the logs a new run ID. Each replay makes a new run, also
   when the original run exists.
2. Files the run under the path, with the next free build number.
3. Makes your Argus user the starter and the assignee of the run.
4. Keeps the logs of the run. The log links point to the original S3 objects.
5. Records the original run ID on the new run. The run page shows
   "Replayed from" with a link to the original run.

When the group or the test of the path does not exist, the run fails with an
error that names the missing parts. Add `--create-missing-tests` to create
them. A replay never creates a release for `--build-id`.

Turn off a step that you do not want:

| Flag | Effect |
| ---- | ------ |
| `--as-me=false` | Keep the recorded starter and the scheduled assignee. |
| `--backfill-logs=false` | Attach only the logs that the replay log records. |

`--as-me` also works without `--build-id`. It then makes you the assignee of
the runs that the logs name, and writes the change to the run activity. The
runs keep their original run IDs and their recorded starter.

### Finish a replay that failed

When a replay into a build path fails part way, run it again with `--resume`
and the run ID of the new run. The replay then writes into that run in place
of a new one. Give the same `--build-id` as the first replay, or none for a
local run in `local-runs`:

```bash
argus run replay --file argus-replay-baseline.tar.zst \
  --build-id scylla-staging/jdoe/my-argus-local-run \
  --resume 7f3e2a6c-5b1d-4c8e-9a0f-2d4b6c8e0a1f
```

The logs must hold one run, and the run you resume must be the copy of that
run under the same `--build-id`. The run keeps its build number. The server applies every record again. An
event or a resource that the first replay wrote is written to the same row.

### Output

The summary counts the records. One line per run follows, with its link in
Argus:

```
Replay summary: total=83 processed=83 succeeded=83 failed=0 skipped=0 backfilled_logs=2
Run 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 -> 7f3e2a6c-5b1d-4c8e-9a0f-2d4b6c8e0a1f (scylla-staging/jdoe/my-argus-local-run#1): https://argus.scylladb.com/tests/scylla-cluster-tests/7f3e2a6c-5b1d-4c8e-9a0f-2d4b6c8e0a1f
```

The first ID is the run ID in the log, and the second ID is the run ID in
Argus. The build follows in parentheses. Without `--build-id` the two IDs are
the same, and the line shows one ID.
A table of errors follows when a record fails. `--report json` writes the
summary and the links as JSON.

Run with `--dry-run` first to check the logs and the build path. A dry run
applies nothing and shows no links. It shows the build each run would get:

```
Run 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 would replay as (scylla-staging/jdoe/my-argus-local-run#2)
```

Use `--target-url` to replay into another Argus instance. The CLI must already
hold credentials for that instance.

## Authentication

**This is where most people get stuck.** Read this section before running any command.

### How it works

The CLI needs two things to talk to Argus:

1. A **Personal Access Token (PAT)** — a long-lived token stored in your system keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service / `pass`).
2. A **Cloudflare Access credential** — required only when Argus is behind Cloudflare Access (the default for production at `argus.scylladb.com`).

The first time you run `argus auth`, it fetches both automatically and stores them. Subsequent commands pull them from the keychain silently. If a credential expires, the CLI re-authenticates transparently and retries.

### Cloudflared: what it is and when you need it

`cloudflared` is Cloudflare's tunnel client. The CLI uses it to obtain a short-lived JWT that proves to Cloudflare Access that you are allowed through the firewall before your request ever reaches Argus.

**You need cloudflared when:**
- Connecting to `argus.scylladb.com` or any other Argus instance protected by Cloudflare Access.
- Running `argus auth` (browser-based login).

**You do NOT need cloudflared when:**
- Connecting to `localhost` or any loopback address — the CLI detects this automatically and skips all Cloudflare logic.
- Using a service-account (headless) setup with `CF-Access-Client-Id` / `CF-Access-Client-Secret` credentials.
- Running in CI/CD where you set `ARGUS_AUTH_TOKEN` or `ARGUS_TOKEN` directly.
- You explicitly disable it (see [Bypassing Cloudflare](#bypassing-cloudflare) below).

**The CLI manages cloudflared for you.** It checks `$PATH`, then its own cache at `$XDG_CACHE_HOME/argus-cli/cloudflared`, and downloads the latest release from GitHub if neither is found. You do not need to install it manually.

### Auth modes

#### Mode 1 — Browser login (default, interactive)

For humans authenticating against a production Argus behind Cloudflare Access.

```
argus auth
```

Flow:
1. Checks keychain — exits early if credentials are still valid.
2. Invokes `cloudflared access login` — opens a browser window for Cloudflare Access SSO.
3. Asks Argus about the PAT already in the keychain, if any (`GET /api/v1/user/token` authenticated with that token). A token Argus accepts that has not expired is kept and the flow stops here.
4. Otherwise exchanges the resulting JWT for an Argus session.
5. Converts the session into a PAT valid for 14 days and stores it in the keychain.

You only need to do this once. After that, every command works without re-authentication.

#### Mode 2 — Headless / service-account (servers and CI)

**If you are running on a server or in CI, this is the only supported mode.**

The keychain-based modes (browser login and `argus auth-token`) require a system keychain daemon — macOS Keychain, Windows Credential Manager, or Linux Secret Service / `pass`. Most servers and CI runners do not have one. Without it, any command that tries to read from the keychain fails silently and the CLI has no credentials to send.

The solution is to skip the keychain entirely and supply credentials through environment variables:

```bash
export ARGUS_CF_ACCESS_CLIENT_ID=your-client-id
export ARGUS_CF_ACCESS_CLIENT_SECRET=your-client-secret
export ARGUS_AUTH_TOKEN=your-pat
```

Set these in your CI secret store or server environment and every `argus` command will pick them up automatically — no `argus auth` step, no keychain, no browser.

To get a service-account client ID and secret, ask your Cloudflare Access administrator. To get an Argus PAT, run `argus auth` once on a developer machine and copy the token out of the keychain, or have an admin generate one via the Argus web UI.

On a machine that **does** have a keychain, `argus auth headless` stores all three interactively:

```
argus auth headless
```

Prompts (masked) for the CF Access Client ID, CF Access Client Secret, and Argus PAT, then writes them to the keychain and sets `use_cloudflare: false` in the config file. After that, the CLI sends the CF Access service-account headers on every request instead of invoking `cloudflared`.

#### Mode 3 — Direct token (local / dev)

For local Argus instances or any deployment without Cloudflare Access.

```
argus auth-token <your-token>
```

Stores the PAT directly. Cloudflare is never consulted. This is equivalent to setting `ARGUS_AUTH_TOKEN` but persists the token to the keychain.

### Bypassing Cloudflare

Several mechanisms disable Cloudflare integration. Use whichever fits your workflow:

| Mechanism | Scope | When to use |
|---|---|---|
| Loopback URL (`localhost`, `127.*`, `::1`) | automatic | Local dev — no action needed |
| `ARGUS_DISABLE_CLOUDFLARE=true` | env var, process-wide | CI/CD, scripts, one-off commands (also settable via `argus config set use_cloudflare false`) |
| `--disable-cloudflare` flag | single command | Ad-hoc overrides |
| `argus config set use_cloudflare false` | config file, persistent | When you always connect without CF |

### Credential priority

Credentials are layered — later sources override earlier ones, so environment variables always win over the keychain.

**Cloudflared mode** (default, `use_cloudflare: true`):

1. PAT from keychain
2. Session cookie from keychain — fallback when no PAT is stored
3. CF Access JWT from `cloudflared` — fetched alongside #1 or #2; required by the CF firewall
4. `ARGUS_AUTH_TOKEN` env var — overrides keychain PAT / session
5. `ARGUS_TOKEN` env var — fallback if `ARGUS_AUTH_TOKEN` is unset
6. `ARGUS_CF_ACCESS_CLIENT_ID` + `ARGUS_CF_ACCESS_CLIENT_SECRET` — overrides the cloudflared JWT

**Headless mode** (`use_cloudflare: false`):

1. PAT from keychain
2. CF service-account bundle from keychain — fallback when no PAT is stored (holds both CF headers and an Argus PAT, stored by `argus auth headless`)
3. `ARGUS_AUTH_TOKEN` env var — overrides keychain PAT
4. `ARGUS_TOKEN` env var — fallback if `ARGUS_AUTH_TOKEN` is unset
5. `ARGUS_CF_ACCESS_CLIENT_ID` + `ARGUS_CF_ACCESS_CLIENT_SECRET` — overrides CF headers from keychain

### Logging out

```
argus auth logout
```

Removes all stored credentials (PAT, session, CF service-account bundle) from the system keychain.

## Configuration

Config file lives at `$XDG_CONFIG_HOME/argus-cli/config.yaml` (on Linux: `~/.config/argus-cli/config.yaml`). It is created with defaults on first run.

```yaml
url: https://argus.scylladb.com
use_cloudflare: true
```

Manage it with:

```bash
argus config list
argus config get url
argus config set url https://my-argus.internal
argus config set use_cloudflare false
```

---

## Storage locations

| Purpose | Path |
|---|---|
| Config file | `$XDG_CONFIG_HOME/argus-cli/config.yaml` |
| Cached responses | `$XDG_CACHE_HOME/argus-cli/cache/` |
| Cloudflared binary | `$XDG_CACHE_HOME/argus-cli/cloudflared` |
| Logs | `$XDG_CACHE_HOME/argus-cli/logs/` |
| Credentials | System keychain |

On Linux `$XDG_CONFIG_HOME` defaults to `~/.config` and `$XDG_CACHE_HOME` to `~/.cache`.
