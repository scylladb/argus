# Argus CLI — Installation Guide

## Step 1: Check if already installed and up to date

```bash
echo "installed: $(argus version 2>/dev/null || echo 'not installed')"
echo "latest:    $(curl -sL https://api.github.com/repos/scylladb/argus/releases | grep -oP '"tag_name":\s*"cli/v\K[^"]+' | head -1)"
```

If the installed version matches the latest, stop here. Otherwise continue.

## Step 2: Install or upgrade

Set the version to install (use the latest from Step 1):

```bash
VERSION=0.1.2
```

### Linux amd64

```bash
curl -sL "https://github.com/scylladb/argus/releases/download/cli/v${VERSION}/argus_${VERSION}_linux_amd64.tar.gz" | tar xz -C ~/.local/bin argus
```

### macOS amd64

```bash
curl -sL "https://github.com/scylladb/argus/releases/download/cli/v${VERSION}/argus_${VERSION}_macOS_amd64.tar.gz" | tar xz -C ~/.local/bin argus
```

## Step 3: Verify

```bash
export PATH="$HOME/.local/bin:$PATH"
argus version
```

## Configuration

The CLI reads `~/.config/argus/config.yaml`. Run `argus configure` to set up interactively.

## All releases

https://github.com/scylladb/argus/releases?q=cli
