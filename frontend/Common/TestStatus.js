import {faBan, faEye, faEyeSlash, faSearch} from "@fortawesome/free-solid-svg-icons";

export const TestStatus = {
    PASSED: "passed",
    FAILED: "failed",
    RUNNING: "running",
    ERROR: "error",
    CREATED: "created",
    ABORTED: "aborted",
    NOT_RUN: "not_run",
    TEST_ERROR: "test_error",
    NOT_PLANNED: "not_planned",
    UNKNOWN: "unknown",
};

export const TestStatusFilterDefaultState = {
    "created": true,
    "running": true,
    "failed": true,
    "test_error": true,
    "error": true,
    "passed": true,
    "aborted": true,
    "not_run": true,
    "not_planned": true,
    "unknown": true,
    "skipped": true,
};

export const TestStatusChangeable = {
    FAILED: "failed",
    TEST_ERROR: "test_error",
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
    "test_error": "bg-test-error",
    "error": "bg-danger",
    "passed": "bg-success",
    "aborted": "bg-dark",
    "not_run": "bg-secondary",
    "not_planned": "bg-not-planned",
    "unknown": "bg-dark",
    "skipped": "bg-dark"
};

export const StatusTableBackgroundCSSClassMap = {
    "created": "table-info",
    "running": "table-warning",
    "failed": "table-danger",
    "test_error": "table-orange",
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
    "test_error": "text-test-error",
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
    "test_error": "btn-orange",
    "error": "btn-danger",
    "passed": "btn-success",
    "aborted": "btn-dark",
    "not_run": "btn-secondary",
    "not_planned": "btn-secondary",
    "unknown": "btn-secondary"
};

export const StatusSortPriority = {
    failed: 0,
    test_error: 0,
    error: 1,
    aborted: 2,
    passed: 4,
    running: 5,
    created: 6,
    none: 7,
    skipped: 9,
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
    "test_error": "#e65c00",
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

export const NemesisStatusBg = {
    "started": "bg-info",
    "running": "bg-warning",
    "failed": "bg-danger",
    "skipped": "bg-dark",
    "succeeded": "bg-success",
};

export const NemesisStatusFg = {
    "started": "text-dark",
    "running": "text-dark",
    "failed": "text-light",
    "skipped": "text-light",
    "succeeded": "text-light",
};

export const ResultCellStatusStyleMap = {
    "PASS": "table-success",
    "ERROR": "table-danger",
    "WARNING": "table-warning",
    "NULL": "table-secondary"
};

export const NemesisStatusToTestStatus = {
    "skipped": "aborted",
    "succeeded": "passed",
};

export const PytestStatus = {
    PASSED: "passed",
    FAILURE: "failure",
    SKIPPED: "skipped",
    ERROR: "error",
    XFAILED: "xfailed",
    XPASS: "xpass",
    PASSED_ERROR: "passed & error",
    FAILURE_ERROR: "failure & error",
    SKIPPED_ERROR: "skipped & error",
    ERROR_ERROR: "error & error",
};

export const PytestColors = {
    [PytestStatus.PASSED]: "#198754",
    [PytestStatus.FAILURE]: "#dc3545",
    [PytestStatus.ERROR]: "#ffc107",
    [PytestStatus.SKIPPED]: "#212529",
    [PytestStatus.XFAILED]: "#f8f9fa",
    [PytestStatus.XPASS]: "#f8f9fa",
    [PytestStatus.PASSED_ERROR]: "#ffc107",
    [PytestStatus.FAILURE_ERROR]: "#dc3545",
    [PytestStatus.SKIPPED_ERROR]: "#212529",
    [PytestStatus.ERROR_ERROR]: "#ffc107",
};

export const PytestBgStyles = {
    [PytestStatus.PASSED]: "bg-success",
    [PytestStatus.FAILURE]: "bg-danger",
    [PytestStatus.ERROR]: "bg-warning",
    [PytestStatus.SKIPPED]: "bg-dark",
    [PytestStatus.XFAILED]: "bg-light",
    [PytestStatus.XPASS]: "bg-light",
    [PytestStatus.PASSED_ERROR]: "bg-warning",
    [PytestStatus.FAILURE_ERROR]: "bg-danger",
    [PytestStatus.SKIPPED_ERROR]: "bg-dark",
    [PytestStatus.ERROR_ERROR]: "bg-warning",
};

export const PytestFgStyles = {
    [PytestStatus.PASSED]: "text-success",
    [PytestStatus.FAILURE]: "text-danger",
    [PytestStatus.ERROR]: "text-warning",
    [PytestStatus.SKIPPED]: "text-dark",
    [PytestStatus.XFAILED]: "text-light",
    [PytestStatus.XPASS]: "text-light",
    [PytestStatus.PASSED_ERROR]: "text-warning",
    [PytestStatus.FAILURE_ERROR]: "text-danger",
    [PytestStatus.SKIPPED_ERROR]: "text-dark",
    [PytestStatus.ERROR_ERROR]: "text-warning",
};


export const PytestTextStyles = {
    [PytestStatus.PASSED]: "text-light",
    [PytestStatus.FAILURE]: "text-light",
    [PytestStatus.ERROR]: "text-dark",
    [PytestStatus.SKIPPED]: "text-light",
    [PytestStatus.XFAILED]: "text-dark",
    [PytestStatus.XPASS]: "text-dark",
    [PytestStatus.PASSED_ERROR]: "text-dark",
    [PytestStatus.FAILURE_ERROR]: "text-light",
    [PytestStatus.SKIPPED_ERROR]: "text-light",
    [PytestStatus.ERROR_ERROR]: "text-dark",
};

export const PytestBtnStyles = {
    [PytestStatus.PASSED]: "btn-success",
    [PytestStatus.FAILURE]: "btn-danger",
    [PytestStatus.ERROR]: "btn-warning",
    [PytestStatus.SKIPPED]: "btn-dark",
    [PytestStatus.XFAILED]: "btn-light",
    [PytestStatus.XPASS]: "btn-light",
    [PytestStatus.PASSED_ERROR]: "btn-warning",
    [PytestStatus.FAILURE_ERROR]: "btn-danger",
    [PytestStatus.SKIPPED_ERROR]: "btn-dark",
    [PytestStatus.ERROR_ERROR]: "btn-warning",
};
