export const enum PytestStatus {
    ERROR = "error",
    PASSED = "passed",
    FAILURE = "failure",
    SKIPPED = "skipped",
    XFAILED = "xfailed",
    XPASS = "xpass",
    PASSED_ERROR = "passed & error",
    FAILURE_ERROR = "failure & error",
    SKIPPED_ERROR = "skipped & error",
    ERROR_ERROR = "error & error",
}

export const PytestStatuses = [
    PytestStatus.PASSED,
    PytestStatus.FAILURE,
    PytestStatus.ERROR,
    PytestStatus.XFAILED,
    PytestStatus.XPASS,
    PytestStatus.SKIPPED,
    PytestStatus.PASSED_ERROR,
    PytestStatus.FAILURE_ERROR,
    PytestStatus.SKIPPED_ERROR,
    PytestStatus.ERROR_ERROR,
];

export type PytestData = {
    name: string,
    id: string,
    timestamp: number,
    message: string,
    session_timestamp: number,
    test_type: string,
    run_id: string,
    status: PytestStatus,
    duration: number,
    markers: string[],
    user_fields: { [key: string]: string },
};
