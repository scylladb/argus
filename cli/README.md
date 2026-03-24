# Argus CLI

Command-line interface for the Argus test management service. Authenticates
via Cloudflare Access and stores session tokens in the system keychain so
subsequent commands work without re-authentication.

## Prerequisites

- Go 1.25+ (build only)
- A browser (Cloudflare Access opens one during login)
- Linux: a Secret Service provider (GNOME Keyring, KWallet, etc.)

`cloudflared` is downloaded automatically if it is not already on your PATH.

## Installation

```bash
cd cli
make build
```

The binary is written to `cli/bin/argus`. Move it somewhere on your PATH or
run it directly:

```bash
./bin/argus --help
```

## Authentication

Before using any command that talks to Argus, authenticate once:

```bash
argus auth
```

This will:

1. Locate (or download) the `cloudflared` binary.
2. Open a browser window for Cloudflare Access login.
3. Exchange the resulting JWT for an Argus session token.
4. Store both tokens in your system keychain (macOS Keychain, Windows
   Credential Manager, or Linux Secret Service).

On subsequent runs the cached tokens are reused automatically. When the
Cloudflare JWT expires, `argus auth` re-opens the browser.

### Pointing to a different Argus instance

```bash
argus --url https://argus-staging.example.com auth
```

Or set it permanently:

```bash
export ARGUS_URL=https://argus-staging.example.com
argus auth
```

Or edit the config file (see below).

## Configuration

On first run, a config file is created at:

```
$XDG_CONFIG_HOME/argus-cli/config.yaml   # typically ~/.config/argus-cli/config.yaml
```

Contents:

```yaml
url: https://argus.scylladb.com
```

### Precedence

Values are resolved in this order (highest wins):

1. CLI flags (`--url`)
2. Environment variables (`ARGUS_URL`)
3. Config file
4. Built-in defaults

## Global Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | `https://argus.scylladb.com` | Argus service base URL |
| `--config` | (auto) | Path to config file |
| `--text` | `false` | Render output as a text table instead of JSON |
| `--log-level` | `info` | Log verbosity: `trace`, `debug`, `info`, `warn`, `error` |

## Commands

| Command | Description |
|---------|-------------|
| `argus auth` | Authenticate with Argus via Cloudflare Access |

## Troubleshooting

### Log file

All output is appended to:

```
$XDG_CACHE_HOME/argus-cli/argus-cli.log   # typically ~/.cache/argus-cli/argus-cli.log
```

Increase verbosity with `--log-level debug` (or `trace` for maximum detail).

### Clearing cached credentials

If authentication gets into a bad state, clear the keychain entries and
re-authenticate:

**Linux (Secret Service / GNOME Keyring):**

```bash
secret-tool clear service argus-cli
argus auth
```

**macOS:**

Open Keychain Access, search for "argus-cli", delete the entries, then
re-run `argus auth`.

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `cloudflared: unsupported platform` | No pre-built binary for your OS/arch | Install `cloudflared` manually and put it on PATH |
| `auth: cloudflared access login failed` | Browser auth didn't complete | Re-run `argus auth`; check your browser |
| `auth: no session cookie in login response` | Argus rejected the CF token | Ensure the Argus URL is correct (`--url`) |
