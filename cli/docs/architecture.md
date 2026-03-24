# Argus CLI Architecture

## Overview

The CLI is a Go binary built on [cobra](https://github.com/spf13/cobra). It
authenticates users via Cloudflare Access and will eventually expose Argus API
operations (listing runs, viewing results, etc.) as subcommands.

## Package Layout

```
cli/
├── main.go                  Entry point: signal handling, exit codes
├── cmd/                     Cobra command definitions
│   ├── root.go              Root command, global flags, PersistentPreRunE
│   ├── auth.go              `argus auth` command
│   └── context.go           Typed context helpers (Config, Logger, API client, etc.)
└── internal/
    ├── api/                 HTTP client for the Argus API
    ├── auth/                Cloudflare + Argus authentication flows
    ├── config/              Viper-based configuration, XDG paths
    ├── jwt/                 Lightweight JWT expiry checking (no signature verification)
    ├── keychain/            OS keychain integration (go-keyring)
    ├── logging/             Zerolog setup, file + stderr fan-out
    ├── models/              Typed structs for API responses
    ├── output/              Output abstraction (JSON or text table)
    └── services/            External binary management (cloudflared download/cache)
```

## Command Lifecycle

Every subcommand inherits from `rootCmd`, whose `PersistentPreRunE` runs
before any subcommand and wires up shared resources:

```
PersistentPreRunE
  │
  ├─ 1. Logging     → logging.Setup(level, commandPath)
  │                    Stores logger + cleanup func on context
  │
  ├─ 2. Output      → output.New(writer, useText)
  │                    Stores Outputter on context
  │
  ├─ 3. Config      → config.Load(cfgFile, cmd)
  │                    Reads YAML + env + flags; stores Config on context
  │
  ├─ 4. Keychain    → keychain.Load()
  │                    Best-effort: attaches session to API client if found
  │
  └─ 5. API client  → api.New(cfg.URL, opts...)
                       Stores Client on context
```

Subcommands retrieve these via typed helpers that panic on missing values
(fail-fast during development):

```go
cfg    := ConfigFrom(ctx)       // *config.Config
log    := LoggerFrom(ctx)       // zerolog.Logger
out    := OutputterFrom(ctx)    // output.Outputter
client := APIClientFrom(ctx)    // *api.Client
```

## Authentication Flow

```
argus auth
  │
  ├─ 1. Locate cloudflared
  │     PATH lookup → cached binary → download from GitHub releases
  │
  ├─ 2. Check keychain for existing Argus session
  │     Found → return (no network calls)
  │
  ├─ 3. Check keychain for cached CF Access JWT
  │     Found + not expired → skip to step 5
  │
  ├─ 4. Run `cloudflared access login`
  │     Opens browser → user authenticates → JWT on stdout
  │     Store JWT in keychain
  │
  └─ 5. Exchange CF JWT for Argus session
        POST /auth/login/cf with CF_Authorization cookie
        Extract session cookie from response
        Store session in keychain
```

Token storage uses the OS keychain (service name `argus-cli`):

| Account key | Content | Lifetime |
|-------------|---------|----------|
| `session` | Argus session cookie | Until server invalidates |
| `cf_token` | Cloudflare Access JWT | Until JWT `exp` claim |

## Configuration System

Configuration is managed by [Viper](https://github.com/spf13/viper) with
automatic flag binding.

**Precedence (highest wins):** flags > env vars (`ARGUS_*`) > config file > defaults.

The config file lives at `$XDG_CONFIG_HOME/argus-cli/config.yaml` and is
auto-created on first run with the resolved defaults.

### Adding a new config key

1. Add a field to `Config` in `internal/config/config.go`:

   ```go
   type Config struct {
       URL     string `mapstructure:"url"`
       Timeout int    `mapstructure:"timeout"`  // new
   }
   ```

2. Register the key in the `configKeys` map (same file):

   ```go
   var configKeys = map[string]struct{}{
       "url":     {},
       "timeout": {},  // new
   }
   ```

3. Set a default in `Load()`:

   ```go
   v.SetDefault("timeout", 30)
   ```

4. Add the corresponding persistent flag in `cmd/root.go`:

   ```go
   rootCmd.PersistentFlags().IntVar(&timeout, "timeout", 30, "request timeout in seconds")
   ```

That's it. Viper's auto-binding (the `VisitAll` loop in `Load`) picks up any
persistent flag whose name appears in `configKeys`.

## API Client

`internal/api` provides a generic HTTP client scoped to a base URL.

Key design points:

- **Functional options** for construction: `WithSession`, `WithCFToken`,
  `WithAPIToken`, `WithHTTPClient`.
- **`DoJSON[T]`** is a package-level generic function (not a method, because
  Go does not allow additional type parameters on methods). It reads the
  response body (capped at 10 MB), checks HTTP status for non-JSON error
  responses, and decodes the `APIResponse[T]` envelope.
- **`APIResponse[T]`** uses `json.RawMessage` for lazy decode — the envelope
  is parsed first, then the payload is decoded into `T` only on success.

## Output System

Commands write results through an `Outputter` interface:

```go
type Outputter interface {
    Write(v any) error
}
```

Two implementations:

- **JSON** (default): `json.MarshalIndent` to stdout.
- **Text** (`--text`): renders as a table using `tablewriter`. Values must
  implement the `Tabular` interface (returns `Headers()` and `Rows()`).
  Non-Tabular values fall back to a single-column JSON table.

## Testing Patterns

- **Functional options everywhere.** Every package that makes network calls or
  touches the filesystem accepts option functions for injecting mocks.
- **`httptest.Server`** for API and download tests.
- **Mock keyring.** Tests call `keyring.MockInit()` to replace the real
  keychain with an in-memory store.
- **Fake binaries.** Auth tests compile small Go programs on the fly
  (`fakeCFBin`) that simulate `cloudflared` output.
- **Context helpers.** `cmd/export_test.go` re-exports context constructors
  so tests outside `cmd` can build realistic contexts.

## How to Add a New Command

Example: adding `argus runs list`.

### 1. Create the command file

Create `cmd/runs.go`:

```go
package cmd

import (
    "github.com/scylladb/argus/cli/internal/api"
    "github.com/scylladb/argus/cli/internal/logging"
    "github.com/scylladb/argus/cli/internal/models"
    "github.com/spf13/cobra"
)

var runsCmd = &cobra.Command{
    Use:   "runs",
    Short: "Manage test runs",
}

var runsListCmd = &cobra.Command{
    Use:   "list",
    Short: "List recent test runs",
    RunE: func(cmd *cobra.Command, _ []string) error {
        ctx := cmd.Context()
        client := APIClientFrom(ctx)
        out := OutputterFrom(ctx)
        log := logging.For(LoggerFrom(ctx), "runs")

        req, err := client.NewRequest(ctx, "GET", "/api/v1/runs", nil)
        if err != nil {
            return err
        }

        runs, err := api.DoJSON[[]models.RunBase](client, req)
        if err != nil {
            log.Error().Err(err).Msg("failed to list runs")
            return err
        }

        return out.Write(runs)
    },
}

func init() {
    runsCmd.AddCommand(runsListCmd)
    rootCmd.AddCommand(runsCmd)
}
```

### 2. Make the response type implement `Tabular` (optional)

If you want `--text` output to render a table, implement the `Tabular`
interface on your model type in `internal/models/`:

```go
func (r RunBase) Headers() []string {
    return []string{"ID", "Status", "Start Time"}
}

func (r RunBase) Rows() [][]string {
    return [][]string{{r.ID, string(r.Status), r.StartTime}}
}
```

For slices, create a wrapper type:

```go
type RunList []RunBase

func (rl RunList) Headers() []string { return RunBase{}.Headers() }
func (rl RunList) Rows() [][]string {
    rows := make([][]string, len(rl))
    for i, r := range rl {
        rows[i] = r.Rows()[0]
    }
    return rows
}
```

### 3. Add tests

Create `cmd/runs_test.go` using `httptest.Server` to mock the API and verify
both JSON and text output paths.

### Checklist

- [ ] Command file in `cmd/` with `init()` registering it
- [ ] Response types in `internal/models/` (if new)
- [ ] `Tabular` implementation for `--text` support (if applicable)
- [ ] Tests covering happy path and error cases
- [ ] If new config keys are needed, follow the config section above
