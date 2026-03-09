import { PytestTab, PytestRun } from "../Pytest";
import DtestTab from "../Pytest/DtestTab.svelte";
import TestPyTab from "../Pytest/TestPyTab.svelte";

export const Cases = {
    PYTEST: "pytest",
    DTEST: "dtest",
    TESTPY: "testpy",
};

export const Tabs = {
    [Cases.PYTEST]: PytestTab,
    [Cases.DTEST]: DtestTab,
    [Cases.TESTPY]: TestPyTab,
};

export const TabBody = {
    [Cases.PYTEST]: PytestRun,
    [Cases.DTEST]: PytestRun,
    [Cases.TESTPY]: PytestRun,
};
