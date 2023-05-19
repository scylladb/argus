import { faBan, faEye, faEyeSlash, faSearch } from "@fortawesome/free-solid-svg-icons";

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
    IGNORED: "ignored",
};

export const InvestigationStatusIcon = {
    in_progress: faSearch,
    not_investigated: faEyeSlash,
    investigated: faEye,
    ignored: faBan,
};

export const InvestigationButtonCSSClassMap = {
    "in_progress": "btn-warning",
    "not_investigated": "btn-danger",
    "investigated": "btn-success",
    "ignored": "btn-dark"
};

export const InvestigationBackgroundCSSClassMap = {
    "in_progress": "bg-warning",
    "not_investigated": "bg-danger",
    "investigated": "bg-success",
    "ignored": "bg-dark"
};


export const TestInvestigationStatusStrings = {
    "in_progress": "In progress",
    "not_investigated": "Not Investigated",
    "investigated": "Investigated",
    "ignored": "Ignored",
};

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

export const StatusTableBackgroundCSSClassMap = {
    "created": "table-info",
    "running": "table-warning",
    "failed": "table-danger",
    "error": "table-danger",
    "skipped": "table-dark",
    "passed": "table-success",
    "aborted": "table-dark",
    "not_run": "table-secondary",
    "not_planned": "table-not-planned",
    "unknown": "table-dark"
};


export const StatusCSSClassMap = {
    "created": "text-info",
    "running": "text-warning",
    "failed": "text-danger",
    "error": "table-danger",
    "skipped": "table-dark",
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
    error: 1,
    aborted: 2,
    skipped: 3,
    passed: 4,
    running: 5,
    created: 6,
    none: 7,
    not_run: 10,
    not_planned: 20,
    unknown: 999,
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
};

export const NemesisStatuses = {
    STARTED: "started",
    RUNNING: "running",
    FAILED: "failed",
    SKIPPED: "skipped",
    SUCCEEDED: "succeeded",
};

export const NemesisStatusBackgrounds = {
    "started": "table-info",
    "running": "table-warning",
    "failed": "table-danger",
    "skipped": "table-dark",
    "succeeded": "table-success",
};
