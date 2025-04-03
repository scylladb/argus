// Types
export interface TestRun {
    build_id: string;
    version: string;
    status: string;
    duration: number;
    run_id: string;
    start_time: number;
    stack_trace?: string;
    investigation_status: string;
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
