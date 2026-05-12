#!/usr/bin/env bash
# extract-semver.sh — strip the "cli/" prefix from a release tag.
#
# Usage:
#   GITHUB_REF_NAME=cli/v1.2.0 ./extract-semver.sh
#
# Prints the bare semver (e.g. "v1.2.0") to stdout.

set -euo pipefail

TAG="${GITHUB_REF_NAME}"
echo "${TAG#cli/}"
