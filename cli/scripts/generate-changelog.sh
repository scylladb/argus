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
# We use a record separator (RS=0x1E, ASCII "record separator") between
# fields so subjects containing pipes or special chars are handled safely.
# Format per commit: SHA RS subject RS author NL
# ---------------------------------------------------------------------------
FIELD_SEP=$'\x1e'   # ASCII record separator — safe to use as field delimiter

mapfile -t RAW_COMMITS < <(
    git log \
        --no-merges \
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
# Supported types (from the project's Conventional Commits style):
#   feature | feat | fix | refactor | improvement | chore | docs | test | ci
# Pattern: type[(scope)]: description
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

# Store the regex in a variable — avoids quoting pitfalls with bash's =~
CONV_COMMIT_RE='^([a-zA-Z]+)(\([^)]*\))?[[:space:]]*:[[:space:]]*(.+)$'

for raw in "${RAW_COMMITS[@]}"; do
    # Split on the field separator
    IFS="$FIELD_SEP" read -r sha subject author <<< "$raw"
    short_sha="${sha:0:7}"

    # Try to parse as a conventional commit: type[(scope)]: description
    if [[ "$subject" =~ $CONV_COMMIT_RE ]]; then
        type="${BASH_REMATCH[1],,}"   # lowercase the type
        scope="${BASH_REMATCH[2]}"    # parenthesised scope, may be empty
        desc="${BASH_REMATCH[3]}"

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
        type="other"
        formatted_desc="$subject"
    fi

    entry="- ${formatted_desc} (\`${short_sha}\`)"
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
    echo "| \`${short_sha}\` | ${author} | ${subject} |"
done
echo ""
echo "</details>"
