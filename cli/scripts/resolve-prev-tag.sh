#!/usr/bin/env bash
# resolve-prev-tag.sh — find the previous cli/v* tag relative to the current one.
#
# Usage:
#   GITHUB_REF_NAME=cli/v1.2.0 ./resolve-prev-tag.sh
#
# Prints the previous tag name to stdout, or "FIRST" when no prior tag exists.

set -euo pipefail

CURRENT_TAG="${GITHUB_REF_NAME}"

PREV=$(git tag --merged HEAD --list 'cli/v[0-9]*' --sort=version:refname \
         | (grep -v "^${CURRENT_TAG}$" || true) \
         | tail -1)

if [[ -z "$PREV" ]]; then
    PREV="FIRST"
fi

echo "${PREV}"
