/**
 * Numeric-aware version string comparator.
 *
 * Handles versions like "5.2.1", "2024.1.3", "6.0.0~rc1", "5.2.1.dev",
 * and build-metadata suffixes like "-0.20240815.abc1234".
 *
 * Sorting rules:
 *  - Segments are split on "." and compared numerically when possible.
 *  - Build metadata (everything after the first "-") is ignored.
 *  - Pre-release tags (rc, dev) sort BEFORE the corresponding official
 *    release, i.e. 5.2.1.rc1 < 5.2.1.
 */

const NUMERIC_RE = /^\d+$/;

function isNumeric(s: string): boolean {
    return NUMERIC_RE.test(s);
}

function parseVersion(raw: string): string[] {
    // Normalize "~" separator to "."
    let v = raw.replace(/~/g, ".");
    // Strip build metadata after first "-"
    const dashIdx = v.indexOf("-");
    if (dashIdx !== -1) {
        v = v.substring(0, dashIdx);
    }
    return v.split(".");
}

/**
 * Compare two version strings.
 * Returns negative if a < b, positive if a > b, 0 if equal.
 *
 * Pre-release versions (containing non-numeric segments like "rc1", "dev")
 * sort before their corresponding official release:
 *   5.2.1.dev < 5.2.1.rc1 < 5.2.1
 */
export function compareVersions(a: string | null | undefined, b: string | null | undefined): number {
    // Treat null/undefined/empty as "no version" — push to the end.
    const aEmpty = !a;
    const bEmpty = !b;
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;

    const segsA = parseVersion(a);
    const segsB = parseVersion(b);
    const len = Math.max(segsA.length, segsB.length);

    for (let i = 0; i < len; i++) {
        const sa = segsA[i];
        const sb = segsB[i];

        if (sa === undefined && sb === undefined) return 0;

        if (sa === undefined) {
            // A is shorter. If B's extra segment is non-numeric (pre-release),
            // then A (the clean release) is larger.
            return isNumeric(sb!) ? -1 : 1;
        }
        if (sb === undefined) {
            // B is shorter — mirror of above.
            return isNumeric(sa) ? 1 : -1;
        }

        const aNum = isNumeric(sa);
        const bNum = isNumeric(sb);

        if (aNum && bNum) {
            const diff = parseInt(sa, 10) - parseInt(sb, 10);
            if (diff !== 0) return diff;
        } else if (aNum !== bNum) {
            // One numeric, one not: numeric segment is "greater" (official > pre-release tag)
            return aNum ? 1 : -1;
        } else {
            // Both non-numeric: lexicographic
            const cmp = sa.localeCompare(sb);
            if (cmp !== 0) return cmp;
        }
    }

    return 0;
}
