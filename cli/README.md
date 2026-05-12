# Argus CLI

Command-line interface for [Argus](https://argus.scylladb.com) — a test tracking system for automated pipelines. Use it to inspect test runs, fetch logs, stream activity, submit comments, and manage SSH tunnels into Argus clusters.

---

## Authentication

**This is where most people get stuck.** Read this section before running any command.

### How it works

The CLI needs two things to talk to Argus:

1. A **Personal Access Token (PAT)** — a long-lived token stored in your system keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service / `pass`).
2. A **Cloudflare Access credential** — required only when Argus is behind Cloudflare Access (the default for production at `argus.scylladb.com`).

The first time you run `argus auth`, it fetches both automatically and stores them. Subsequent commands pull them from the keychain silently. If a credential expires, the CLI re-authenticates transparently and retries.

---

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

---

### Auth modes

#### Mode 1 — Browser login (default, interactive)

For humans authenticating against a production Argus behind Cloudflare Access.

```
argus auth
```

Flow:
1. Checks keychain — exits early if credentials are still valid.
2. Invokes `cloudflared access login` — opens a browser window for Cloudflare Access SSO.
3. Exchanges the resulting JWT for an Argus session.
4. Converts the session into a durable PAT and stores it in the keychain.

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

---

### Bypassing Cloudflare

Several mechanisms disable Cloudflare integration. Use whichever fits your workflow:

| Mechanism | Scope | When to use |
|---|---|---|
| Loopback URL (`localhost`, `127.*`, `::1`) | automatic | Local dev — no action needed |
| `ARGUS_DISABLE_CLOUDFLARE=true` | env var, process-wide | CI/CD, scripts, one-off commands |
| `--disable-cloudflare` flag | single command | Ad-hoc overrides |
| `argus config set use_cloudflare false` | config file, persistent | When you always connect without CF |

---

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

---

### Logging out

```
argus auth logout
```

Removes all stored credentials (PAT, session, CF service-account bundle) from the system keychain.

---

## Installation

### Pre-built binaries

Download the latest release from the [releases page](https://github.com/scylladb/argus/releases) and place the binary somewhere on your `$PATH`.

### From source

Requires Go 1.25+.

```bash
git clone https://github.com/scylladb/argus
cd argus/cli
go build -o argus .
```

---

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
