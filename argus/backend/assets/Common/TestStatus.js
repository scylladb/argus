export const TestStatus = {
    CREATED: "created",
    RUNNING: "running",
    FAILED: "failed",
    PASSED: "passed",
    ABORTED: "aborted",
};

export const TestStatusChangeable = {
    FAILED: "failed",
    PASSED: "passed",
    ABORTED: "aborted",
};

export const StatusBackgroundCSSClassMap = {
    "created": "bg-info",
    "running": "bg-warning",
    "failed": "bg-danger",
    "passed": "bg-success",
    "aborted": "bg-dark",
    "unknown": "bg-secondary"
};

export const StatusCSSClassMap = {
    "created": "text-info",
    "running": "text-warning",
    "failed": "text-danger",
    "passed": "text-success",
    "aborted": "text-dark",
    "unknown": "text-muted"
};

export const StatusButtonCSSClassMap = {
    "created": "btn-info",
    "running": "btn-warning",
    "failed": "btn-danger",
    "passed": "btn-success",
    "aborted": "btn-dark",
    "unknown": "btn-muted"
};

export const StatusSortPriority = {
    failed: 0,
    aborted: 1,
    passed: 2,
    running: 3,
    created: 4,
    none: 5,
    unknown: 5,
};

export const InProgressStatuses = [
    "created", "running"
];

export const TestStatusColors = {
    "created": "#0dcaf0",
    "running": "#ffc107",
    "failed": "#dc3545",
    "passed": "#198754",
    "aborted": "#212529",
    "unknown": "#6c757d"
}
