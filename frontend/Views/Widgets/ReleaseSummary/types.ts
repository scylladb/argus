import type { Issue } from "../../../Common/IssueTypes";

export interface SummaryCounts {
    executed: number;
    passed: number;
    failed: number;
    aborted: number;
    in_progress: number;
    pending: number;
    issues_new: number;
    issues_existing: number;
    issues_fixed: number;
}

export interface SummaryTest {
    test_id: string;
    group_id: string;
    test_name: string;
    group_name: string;
    status: string;
    run_id: string | null;
    build_id: string | null;
    build_number: number | null;
    version: string | null;
    issues?: number;
    comments?: number;
    start_time?: string | null;
}

export interface SummaryIssue {
    id: string;
    type: "jira" | "github";
    key: string;
    title: string | null;
    url: string | null;
    state: string | null;
    novelty: "new" | "existing";
    status: "open" | "fixed";
    on_latest_run?: boolean;
    open_test_ids?: string[];
    latest_test_ids?: string[];
    test_ids: string[];
    run_ids: string[];
    issue: Issue;
}

export interface Summary {
    version: string | null;
    counts: SummaryCounts;
    tests: SummaryTest[];
    issues: SummaryIssue[];
}

export interface SummaryFamily {
    family: string;
    rollup: Summary;
    versions: Summary[];
}

export interface ReleaseSummaryResponse {
    release_id: string;
    release_name: string;
    generated_at: string | null;
    stale: boolean;
    families: SummaryFamily[];
}
