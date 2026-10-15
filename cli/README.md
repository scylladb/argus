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
local-runs/<your Argus username>/<test>
```

`<test>` is the name of the first SCT config file of the run. For example,
`test-cases/longevity/longevity-100gb-4h.yaml` gives
`local-runs/jdoe/longevity-100gb-4h`. Each replay of the same test adds the
next build: `#1`, `#2`, and so on.

A local run of a test such as `longevity-100gb-4h` often uses a different
config, or belongs to a feature or a pull request. Give `--test` to name the
test yourself:

```bash
argus run replay --dir ~/sct-results/latest --test my-feature
```

The run then goes to `local-runs/<your Argus username>/my-feature`. The
replay replaces each character that a build path does not accept with `-`. To find your local runs in Argus, open the
`local-runs` release and then the group with your username, or search for
`local-runs/<your username>`.

The replay creates the release, the group and the test when they do not
exist. The server picks the build number, and the path always starts with
`local-runs/<your Argus username>/`. You cannot choose the full path, because
a chosen path can name a Jenkins job, and the next Jenkins build would then
get the same number. A Jenkins run keeps its
recorded job path and run ID, so a replay after an outage restores the
original run.

For a local run, the replay:

1. Keeps the recorded run ID, so the logs in S3 stay attached to the run.
2. Files the run under `local-runs/<your Argus username>/<test>`, with the
   next build number of that test. `<test>` is the `--test` value when you
   give it.
3. Makes your Argus user the starter and the assignee of the run.

Only a run that Argus does not hold yet gets the path, the number and the
starter. A run that Argus already holds replays as recorded, and `--as-me`
makes you its assignee.

To replay a local run as recorded, give `--keep-run`. You cannot give
`--keep-run` with `--test`.

Turn off a step that you do not want:

| Flag | Effect |
| ---- | ------ |
| `--as-me=false` | Keep the recorded starter and the scheduled assignee. |
| `--create-missing-tests=false` | Fail when the release, the group or the test of a new run does not exist. |
| `--backfill-logs=false` | Attach only the logs that the replay log records. |

`--as-me` also works for a run that keeps its recorded path. It then makes
you the assignee of the runs that the logs name, and writes the change to the
run activity. The runs keep their original run IDs and their recorded
starter.

### Upload the logs of a local run

A local run does not upload its logs to S3. `hydra collect-logs` uploads them
under the run ID. With Argus off, which is the usual case for a local run,
`collect-logs` does not link the logs to a run in Argus. The replay links
them: the log back-fill lists the S3 prefix of the run ID and attaches each
log that the replay logs do not record.

1. Upload the logs under the run ID:

   ```bash
   hydra collect-logs --test-id 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 \
     --logdir ~/sct-results/<run directory>
   ```

2. Replay the run directory:

   ```bash
   argus run replay --dir ~/sct-results/<run directory>
   ```

When you upload the logs after the first replay, replay again. The second
replay keeps the run and its build, and attaches the new logs. When
`collect-logs` runs with Argus on, it writes its own replay log into the run
directory, and `--dir` sends it with the others.

The back-fill looks in the `cloudius-jenkins-test` bucket, which SCT uses by
default, when the replay logs record no S3 link. A run that uploads to another
bucket needs `REPLAY_LOG_BACKFILL_BUCKET` in the Argus configuration.

### Output

The summary counts the records. One line per run follows, with its link in
Argus:

```
Replay summary: total=83 processed=83 succeeded=83 failed=0 skipped=0 backfilled_logs=0
Run 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 (local-runs/jdoe/longevity-100gb-4h#1): https://argus.scylladb.com/tests/scylla-cluster-tests/91c226dc-a057-4ad4-a0b8-bf8bc73031b9
```

The build follows the run ID in parentheses. A run that keeps its recorded
path shows no build. A run whose `submit_run` failed shows no link, because
Argus may not hold it:

```
Run 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 (local-runs/jdoe/longevity-100gb-4h#1) failed: see the errors below
```

A table of errors follows when a record fails. `--report json` writes the
summary and the links as JSON.

Run with `--dry-run` first to check the logs and the build. A dry run
applies nothing and shows no links. It shows the build each run would get:

```
Run 91c226dc-a057-4ad4-a0b8-bf8bc73031b9 would replay as (local-runs/jdoe/longevity-100gb-4h#1)
```

Use `--target-url` to replay into another Argus instance. The CLI must already
hold credentials for that instance.

## Find the runs linked to an issue

List the test runs linked to a Jira issue key, newest first:

```bash
argus issue runs SCT-1234          # JSON array, one object per run
argus issue runs SCT-1234 --text   # the same rows as a table
argus issue runs SCT-1234 --raw    # the issue and every link field, as returned by the API
```

Each run carries `id`, `test`, `build_id`, `build_number`, `version` (the Scylla version, or the product version when the run reports none), `status`, `start_time` and `argus_url`, the link to the run page. The key may be given in any case. A key that Argus holds no runs for prints an empty list and exits 0. A value that is not an issue key, such as `SCT1234`, is an error.

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
