export const TestStatus = {
    PASSED: "passed",
    FAILED: "failed",
    RUNNING: "running",
    CREATED: "created",
    ABORTED: "aborted",
    NOT_RUN: "not_run",
    NOT_PLANNED: "not_planned",
    UNKNOWN: "unknown",
};

export const TestStatusChangeable = {
    FAILED: "failed",
    PASSED: "passed",
    ABORTED: "aborted",
};


export const TestInvestigationStatus = {
    INVESTIGATED: "investigated",
    NOT_INVESTIGATED: "not_investigated",
    IN_PROGRESS: "in_progress",
};

export const InvestigationButtonCSSClassMap = {
    "in_progress": "btn-warning",
    "not_investigated": "btn-danger",
    "investigated": "btn-success",
};

export const TestInvestigationStatusStrings = {
    "in_progress": "In progress",
    "not_investigated": "Not Investigated",
    "investigated": "Investigated",
}

export const StatusBackgroundCSSClassMap = {
    "created": "bg-info",
    "running": "bg-warning",
    "failed": "bg-danger",
    "passed": "bg-success",
    "aborted": "bg-dark",
    "not_run": "bg-secondary",
    "not_planned": "bg-not-planned",
    "unknown": "bg-dark"
};

export const StatusCSSClassMap = {
    "created": "text-info",
    "running": "text-warning",
    "failed": "text-danger",
    "passed": "text-success",
    "aborted": "text-dark",
    "not_run": "text-secondary",
    "not_planned": "text-not-planned",
    "unknown": "text-muted"
};

export const StatusButtonCSSClassMap = {
    "created": "btn-info",
    "running": "btn-warning",
    "failed": "btn-danger",
    "passed": "btn-success",
    "aborted": "btn-dark",
    "not_run": "btn-secondary",
    "not_planned": "btn-muted",
    "unknown": "btn-muted"
};

export const StatusSortPriority = {
    failed: 0,
    aborted: 1,
    passed: 2,
    running: 3,
    created: 4,
    none: 5,
    not_run: 5,
    not_planned: 5,
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

export const NemesisStatuses = {
    STARTED: "started",
    RUNNING: "running",
    FAILED: "failed",
    SKIPPED: "skipped",
    SUCCEEDED: "succeeded",
}

export const NemesisStatusBackgrounds = {
    "started": "table-info",
    "running": "table-warning",
    "failed": "table-danger",
    "skipped": "table-dark",
    "succeeded": "table-success",
};
