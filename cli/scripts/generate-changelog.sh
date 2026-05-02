#!/usr/bin/env bash
# generate-changelog.sh — produce a Markdown changelog for the Argus CLI.
#
# Only commits that touched files under cli/ are considered.
#
# Usage:
#   ./generate-changelog.sh <from-ref> <to-ref>
#
#   <from-ref>  Git ref of the previous release (tag or commit SHA).
#               Pass "FIRST" to start from the very first commit in the repo.
#   <to-ref>    Git ref of the new release (tag, branch, or SHA).
#               Defaults to HEAD when omitted.
#
# Output:
#   Markdown written to STDOUT; redirect as needed.
#
# Examples:
#   ./generate-changelog.sh cli/v0.1.0 cli/v0.2.0
#   ./generate-changelog.sh cli/v0.1.0 HEAD
#   ./generate-changelog.sh FIRST cli/v0.1.0

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <from-ref> [<to-ref>]" >&2
    exit 1
fi

FROM_REF="$1"
TO_REF="${2:-HEAD}"

# ---------------------------------------------------------------------------
# Build the git log range
# ---------------------------------------------------------------------------
if [[ "$FROM_REF" == "FIRST" ]]; then
    GIT_RANGE="$TO_REF"
else
    GIT_RANGE="${FROM_REF}..${TO_REF}"
fi

# ---------------------------------------------------------------------------
# Collect commits that touched the cli/ subtree.
# --diff-filter=ACDMRT ensures we only include commits that actually added,
# copied, deleted, modified, renamed, or type-changed files under cli/.
# We use a record separator (RS=0x1E, ASCII "record separator") between
# fields so subjects containing pipes or special chars are handled safely.
# Format per commit: SHA RS subject RS author NL
# ---------------------------------------------------------------------------
FIELD_SEP=$'\x1e'   # ASCII record separator — safe to use as field delimiter

mapfile -t RAW_COMMITS < <(
    git log \
        --no-merges \
        --diff-filter=ACDMRT \
        --pretty=format:"%H${FIELD_SEP}%s${FIELD_SEP}%an" \
        "$GIT_RANGE" \
        -- "cli/" 2>/dev/null
)

if [[ ${#RAW_COMMITS[@]} -eq 0 ]]; then
    echo "No CLI commits found in range ${GIT_RANGE}." >&2
    echo "## What's Changed"
    echo ""
    echo "- No changes to the CLI in this release."
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse each commit into type / scope / description
# Best-effort categorisation: if the subject matches a conventional commit
# pattern (type[(scope)][!]: description) we use that; otherwise we try to
# infer the type from common leading keywords.  Anything that cannot be
# categorised lands in "other".
# ---------------------------------------------------------------------------
declare -A SECTIONS
SECTION_ORDER=()

add_to_section() {
    local type="$1"
    local entry="$2"
    if [[ -z "${SECTIONS[$type]+_}" ]]; then
        SECTIONS[$type]=""
        SECTION_ORDER+=("$type")
    fi
    SECTIONS[$type]+="${entry}"$'\n'
}

map_type_to_heading() {
    case "$1" in
        feature|feat)    echo "### Features" ;;
        fix)             echo "### Bug Fixes" ;;
        improvement)     echo "### Improvements" ;;
        refactor)        echo "### Refactoring" ;;
        docs)            echo "### Documentation" ;;
        test)            echo "### Tests" ;;
        chore)           echo "### Chores" ;;
        ci)              echo "### CI" ;;
        *)               echo "### Other Changes" ;;
    esac
}

# Canonical display order for sections
CANONICAL_ORDER=(feature feat fix improvement refactor docs test chore ci other)

# Conventional commit: type[(scope)][!]: description
CONV_COMMIT_RE='^([a-zA-Z]+)(\([^)]*\))?(!)?[[:space:]]*:[[:space:]]*(.+)$'

# Build the GitHub repo URL for commit links.  $GITHUB_REPOSITORY is set by
# Actions (e.g. "owner/repo"); fall back to parsing the remote when running
# locally.
if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
    REPO_URL="https://github.com/${GITHUB_REPOSITORY}"
else
    REPO_URL=$(git remote get-url origin 2>/dev/null \
               | sed -E 's#git@github\.com:#https://github.com/#; s/\.git$//' || true)
fi

for raw in "${RAW_COMMITS[@]}"; do
    # Split on the field separator
    IFS="$FIELD_SEP" read -r sha subject author <<< "$raw"
    short_sha="${sha:0:7}"

    # Try to parse as a conventional commit: type[(scope)][!]: description
    if [[ "$subject" =~ $CONV_COMMIT_RE ]]; then
        type="${BASH_REMATCH[1],,}"   # lowercase the type
        scope="${BASH_REMATCH[2]}"    # parenthesised scope, may be empty
        desc="${BASH_REMATCH[4]}"

        # Strip the leading "(cli)" scope — all commits are already scoped to
        # cli/ so repeating it in the output adds no information.
        scope_clean="${scope//[\(\)]/}"
        scope_clean="${scope_clean#cli}"
        scope_clean="${scope_clean#/}"
        if [[ -n "$scope_clean" ]]; then
            formatted_desc="**${scope_clean}:** ${desc}"
        else
            formatted_desc="${desc}"
        fi
    else
        # Best-effort keyword detection from the subject line
        subject_lower="${subject,,}"
        case "$subject_lower" in
            fix\ *|fix:*|bugfix\ *)        type="fix";         formatted_desc="${subject}" ;;
            feat\ *|feature\ *|add\ *)     type="feat";        formatted_desc="${subject}" ;;
            refactor\ *|refactored\ *)     type="refactor";    formatted_desc="${subject}" ;;
            doc\ *|docs\ *|document\ *)    type="docs";        formatted_desc="${subject}" ;;
            test\ *|tests\ *)             type="test";        formatted_desc="${subject}" ;;
            chore\ *|chore:*)              type="chore";       formatted_desc="${subject}" ;;
            ci\ *|ci:*)                    type="ci";          formatted_desc="${subject}" ;;
            improve*|enhancement\ *)       type="improvement"; formatted_desc="${subject}" ;;
            *)                             type="other";       formatted_desc="${subject}" ;;
        esac
    fi

    # Build the entry with a hyperlinked SHA when we have a repo URL
    if [[ -n "$REPO_URL" ]]; then
        entry="- ${formatted_desc} ([\`${short_sha}\`](${REPO_URL}/commit/${sha}))"
    else
        entry="- ${formatted_desc} (\`${short_sha}\`)"
    fi
    add_to_section "$type" "$entry"
done

# ---------------------------------------------------------------------------
# Resolve a human-readable label for the release header
# ---------------------------------------------------------------------------
if [[ "$TO_REF" == "HEAD" ]]; then
    RELEASE_LABEL="$(git describe --tags --abbrev=0 HEAD 2>/dev/null || echo "HEAD")"
else
    RELEASE_LABEL="$TO_REF"
fi

RELEASE_DATE="$(date -u '+%Y-%m-%d')"

# ---------------------------------------------------------------------------
# Emit Markdown
# ---------------------------------------------------------------------------
echo "## ${RELEASE_LABEL} — ${RELEASE_DATE}"
echo ""
echo "> Changelog includes only commits that touched the \`cli/\` subtree."
echo ""

emitted=()

emit_section() {
    local key="$1"
    if [[ -n "${SECTIONS[$key]+_}" && -n "${SECTIONS[$key]}" ]]; then
        map_type_to_heading "$key"
        echo ""
        printf '%s\n' "${SECTIONS[$key]%$'\n'}"
        echo ""
        emitted+=("$key")
    fi
}

# Emit in canonical order
for key in "${CANONICAL_ORDER[@]}"; do
    emit_section "$key"
done

# Emit any non-canonical types that might have slipped in
for key in "${SECTION_ORDER[@]}"; do
    already=false
    for e in "${emitted[@]:-}"; do
        [[ "$e" == "$key" ]] && { already=true; break; }
    done
    $already || emit_section "$key"
done

# ---------------------------------------------------------------------------
# Full commit list (collapsed detail block for reference)
# ---------------------------------------------------------------------------
echo "---"
echo ""
echo "<details>"
echo "<summary>Full commit list</summary>"
echo ""
echo "| SHA | Author | Subject |"
echo "|-----|--------|---------|"
for raw in "${RAW_COMMITS[@]}"; do
    IFS="$FIELD_SEP" read -r sha subject author <<< "$raw"
    short_sha="${sha:0:7}"
    if [[ -n "$REPO_URL" ]]; then
        echo "| [\`${short_sha}\`](${REPO_URL}/commit/${sha}) | ${author} | ${subject} |"
    else
        echo "| \`${short_sha}\` | ${author} | ${subject} |"
    fi
done
echo ""
echo "</details>"
