import type { SummaryTest } from "../Views/Widgets/ReleaseSummary/types";

interface DashboardTestEntry {
    test: { id: string; name: string; build_system_id: string };
    status: string;
    start_time: number;
    last_runs: unknown[];
}

interface DashboardStats {
    groups?: Record<string, { group: { name: string }; tests?: Record<string, DashboardTestEntry> }>;
}

export interface TestSelection {
    name: string;
    id: string;
    assignees: string[];
    group: string;
    status: string;
    start_time: number;
    last_runs: unknown[];
    build_system_id: string | null;
}

export const summaryTestSelection = (stats: DashboardStats | undefined, test: SummaryTest): TestSelection => {
    const group = stats?.groups?.[test.group_id];
    const entry = group?.tests?.[test.test_id];
    if (group && entry) {
        return {
            name: entry.test.name,
            id: entry.test.id,
            assignees: [],
            group: group.group.name,
            status: entry.status,
            start_time: entry.start_time,
            last_runs: entry.last_runs,
            build_system_id: entry.test.build_system_id,
        };
    }
    return {
        name: test.test_name,
        id: test.test_id,
        assignees: [],
        group: test.group_name,
        status: test.status,
        start_time: test.run_id ? (test.start_time ? Date.parse(test.start_time) / 1000 : 1) : 0,
        last_runs: test.run_id
            ? [{
                id: test.run_id, build_number: test.build_number, status: test.status,
                start_time: test.start_time, assignee: null, issues: [], comments: [],
            }]
            : [],
        build_system_id: test.build_id,
    };
};
