// Types
export interface GithubIssue {
    type: "github";
    number: number;
    state: string;
    title: string;
    url: string;
    owner?: string;
    repo?: string;
}

export interface JiraIssue {
    type: "jira";
    state: string;
    summary: string;
    key: string;
    permalink: string;
}

export type Issue = GithubIssue | JiraIssue;

export interface TestRun {
    build_id: string;
    version: string;
    status: string;
    duration: number;
    run_id: string;
    start_time: number;
    stack_trace?: string;
    investigation_status: string;
    assignee?: string;
    issues?: Issue[];
}

export interface RunDetails {
    build_id: string;
    status: string;
    start_time: string;
    assignee: string;
    version: string;
    investigation_status: string;
    issues: Issue[];
}

export interface NemesisData {
    build_id: string;
    run_id: string;
    version: string;
    name: string;
    status: string;
    duration: number;
    start_time: number;
    stack_trace: string;
}

export interface DataResponse {
    test_runs: TestRun[];
    nemesis_data: NemesisData[];
}
