import { StatusSortPriority } from "../../Common/TestStatus";

export type StatusName =
    | "passed"
    | "failed"
    | "running"
    | "error"
    | "created"
    | "aborted"
    | "not_run"
    | "test_error"
    | "not_planned"
    | "unknown";

export interface NamedEntity {
    id: string;
    name: string;
    pretty_name?: string | null;
}

export interface TestSummary {
    status: string;
    investigation_status: string;
    start_time: string | null;
}

export type StatusCounts = Partial<Record<StatusName, number>> & {
    total: number;
    to_investigate?: number;
};

export type GroupSummary = StatusCounts & { tests: Record<string, TestSummary> };

export type ReleaseSummary = StatusCounts & { groups: Record<string, GroupSummary> };

export const displayName = (entity: NamedEntity): string => entity.pretty_name || entity.name;

const statusRank = (status: string | undefined): number =>
    StatusSortPriority[status as keyof typeof StatusSortPriority] ?? StatusSortPriority.none;

export const sortTests = <T extends NamedEntity>(tests: T[], summaries?: Record<string, TestSummary>): T[] =>
    tests.toSorted(
        (left, right) =>
            statusRank(summaries?.[left.id]?.status) - statusRank(summaries?.[right.id]?.status) ||
            displayName(left).localeCompare(displayName(right), undefined, { numeric: true })
    );

export const pinnedFirst = <T extends NamedEntity>(items: T[], pinned: ReadonlySet<string>): T[] => [
    ...items.filter((item) => pinned.has(item.id)),
    ...items.filter((item) => !pinned.has(item.id)),
];

export const duplicateNames = (items: NamedEntity[]): Set<string> => {
    const seen = new Set<string>();
    const duplicates = new Set<string>();
    for (const item of items) {
        const name = displayName(item);
        (seen.has(name) ? duplicates : seen).add(name);
    }
    return duplicates;
};
