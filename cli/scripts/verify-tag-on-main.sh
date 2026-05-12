#!/usr/bin/env bash
# verify-tag-on-main.sh — abort if the current tag is not reachable from master/main.
#
# Usage:
#   GITHUB_REF_NAME=cli/v1.2.0 ./verify-tag-on-main.sh
#
# Exits 0 when the tag is on master/main, 1 otherwise.

set -euo pipefail

TAG_SHA=$(git rev-list -n1 "${GITHUB_REF_NAME}")
for branch in master main; do
    if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
        if git merge-base --is-ancestor "${TAG_SHA}" "origin/${branch}"; then
            echo "Tag ${GITHUB_REF_NAME} (${TAG_SHA}) is on ${branch}. Proceeding."
            exit 0
        fi
    fi
done
echo "ERROR: Tag ${GITHUB_REF_NAME} is not reachable from master/main. Aborting release." >&2
exit 1
