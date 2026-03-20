import { PytestRun } from "../Pytest";

export const Cases = {
    PYTEST: "pytest",
    DTEST: "dtest",
    TESTPY: "testpy",
};

export const TabMeta = {
    [Cases.PYTEST]: { key: Cases.PYTEST, label: "PyTest" },
    [Cases.DTEST]: { key: Cases.DTEST, label: "DTest" },
    [Cases.TESTPY]: { key: Cases.TESTPY, label: "test.py" },
};

export const TabBody = {
    [Cases.PYTEST]: PytestRun,
    [Cases.DTEST]: PytestRun,
    [Cases.TESTPY]: PytestRun,
};
