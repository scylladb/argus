# Argus

Argus is a test tracking system for automated pipelines. It helps teams inspect test runs, compare results across runs, track events and failures, and understand resource usage for long-running test infrastructure.

## Quick Links

- Full CLI guide: [`cli/README.md`](cli/README.md)
- REST API usage: [`docs/api_usage.md`](docs/api_usage.md)
- Local development setup: [`docs/dev-setup.md`](docs/dev-setup.md)
- Production deployment: [`docs/deployment.md`](docs/deployment.md)

## Install the CLI

Download the latest CLI release into `~/.local/bin`:

### Linux amd64

```bash
VERSION=$(curl -sL https://api.github.com/repos/scylladb/argus/releases | grep -oP '"tag_name":\s*"cli/v\K[^"]+' | head -1)
mkdir -p ~/.local/bin
curl -sL "https://github.com/scylladb/argus/releases/download/cli/v${VERSION}/argus_${VERSION}_linux_amd64.tar.gz" | tar xz -C ~/.local/bin argus
export PATH="$HOME/.local/bin:$PATH"
```

### macOS amd64

```bash
VERSION=$(curl -sL https://api.github.com/repos/scylladb/argus/releases | grep -oP '"tag_name":\s*"cli/v\K[^"]+' | head -1)
mkdir -p ~/.local/bin
curl -sL "https://github.com/scylladb/argus/releases/download/cli/v${VERSION}/argus_${VERSION}_macOS_amd64.tar.gz" | tar xz -C ~/.local/bin argus
export PATH="$HOME/.local/bin:$PATH"
```

Verify the install:

```bash
argus version
```

## First Successful Command

Authenticate against the default production Argus instance:

```bash
argus auth
```

This opens a browser-based login flow when needed and stores credentials for later commands.

If you are running in CI, on a server, or against a local instance, use the auth mode documented in [`cli/README.md`](cli/README.md).

## Use the CLI

Typical next commands:

```bash
argus config list
argus auth logout
```

For authentication modes, Cloudflare behavior, configuration, and command usage, see [`cli/README.md`](cli/README.md).

## Use the API

Generate an API token from your Argus profile page, then call the API with:

```bash
curl --request GET \
  --url https://argus.scylladb.com/api/v1/client/driver_matrix/test_report?buildId=example/driver-matrix/test \
  --header "Authorization: token <YOUR_TOKEN>"
```

Full endpoint details and payload examples live in [`docs/api_usage.md`](docs/api_usage.md).

## Local Development

For local setup, dependencies, ScyllaDB, seed data, and daily workflow, see [`docs/dev-setup.md`](docs/dev-setup.md).

## Production Deployment

For source-based production installation, nginx, systemd, and logging setup, see [`docs/deployment.md`](docs/deployment.md).

## Contributing

Review the [Repository Guidelines](AGENTS.md) for project structure, tooling expectations, and pull request practices before submitting changes.
