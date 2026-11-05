import humanizeDuration from "humanize-duration";
import { StatusBadgeCSSClassMap } from "../../../Common/TestStatus";
import { compareVersions } from "../../../Common/versionSort";
import type { SummaryCounts, SummaryFamily, SummaryTest } from "./types";

export type StatusGroup = "passed" | "failed" | "aborted" | "in_progress" | "pending";
export type StatusFilter = Record<StatusGroup, boolean>;

export const STATUS_GROUPS: { group: StatusGroup; label: string; css: string }[] = [
    { group: "passed", label: "Passed", css: "text-bg-success" },
    { group: "failed", label: "Failed", css: "text-bg-danger" },
    { group: "aborted", label: "Aborted", css: "bg-aborted text-white" },
    { group: "in_progress", label: "In progress", css: "text-bg-warning" },
    { group: "pending", label: "Pending", css: "text-bg-secondary" },
];

const GROUP_OF: Record<string, StatusGroup> = {
    passed: "passed",
    failed: "failed",
    test_error: "failed",
    error: "failed",
    aborted: "aborted",
    created: "in_progress",
    running: "in_progress",
    pending: "pending",
};

export function statusGroup(status: string): StatusGroup | undefined {
    return GROUP_OF[status];
}

const BADGES: Record<string, string> = StatusBadgeCSSClassMap;

export function statusBadge(status: string): string {
    return BADGES[status] ?? "text-bg-secondary";
}

export function allStatuses(): StatusFilter {
    return { passed: true, failed: true, aborted: true, in_progress: true, pending: true };
}

export function onlyStatus(group: StatusGroup): StatusFilter {
    return { passed: false, failed: false, aborted: false, in_progress: false, pending: false, [group]: true };
}

export function showsAll(filter: StatusFilter): boolean {
    return Object.values(filter).every(Boolean);
}

export function matchesFilter(status: string, filter: StatusFilter): boolean {
    const group = statusGroup(status);
    return group ? filter[group] : showsAll(filter);
}

export interface BarSegment {
    group: StatusGroup;
    label: string;
    css: string;
    count: number;
    percent: number;
}

export function barSegments(counts: SummaryCounts): BarSegment[] {
    const total = STATUS_GROUPS.reduce((sum, { group }) => sum + counts[group], 0);
    if (total === 0) return [];
    return STATUS_GROUPS.filter(({ group }) => counts[group] > 0).map(({ group, label, css }) => ({
        group, label, css, count: counts[group], percent: (counts[group] / total) * 100,
    }));
}

export function updatedAgo(generatedAt: string | null, now: Date = new Date()): string {
    if (!generatedAt) return "";
    const elapsed = now.getTime() - new Date(generatedAt).getTime();
    if (elapsed < 60_000) return "just now";
    return `${humanizeDuration(elapsed, { round: true, units: ["y", "mo", "w", "d", "h", "m"], largest: 1 })} ago`;
}

export function shortVersion(version: string): string {
    const [, suffix] = version.split("~");
    return suffix ?? "final";
}

export function issueVersions(family: SummaryFamily): Record<string, string[]> {
    const found: Record<string, string[]> = {};
    const versions = [...family.versions].sort((a, b) => compareVersions(a.version, b.version));
    for (const summary of versions) {
        for (const issue of summary.issues) {
            (found[issue.id] ??= []).push(summary.version as string);
        }
    }
    return found;
}

export interface GridRow {
    test: SummaryTest;
    cells: (SummaryTest | undefined)[];
}

export function byGroupAndName(a: SummaryTest, b: SummaryTest): number {
    return a.group_name.localeCompare(b.group_name) || a.test_name.localeCompare(b.test_name);
}

export function gridRows(family: SummaryFamily, filter: StatusFilter): GridRow[] {
    const perVersion = family.versions.map(
        (summary) => new Map(summary.tests.map((test) => [test.test_id, test])),
    );
    return family.rollup.tests
        .filter((test) => matchesFilter(test.status, filter))
        .sort(byGroupAndName)
        .map((test) => ({ test, cells: perVersion.map((tests) => tests.get(test.test_id)) }));
}
