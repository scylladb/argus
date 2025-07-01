import { PytestTab, PytestRun } from "../Pytest";
import DtestTab from "../Pytest/DtestTab.svelte";

export const Cases = {
    PYTEST: "pytest",
    DTEST: "dtest",
};

export const Tabs = {
    [Cases.PYTEST]: PytestTab,
    [Cases.DTEST]: DtestTab,
};

export const TabBody = {
    [Cases.PYTEST]: PytestRun,
    [Cases.DTEST]: PytestRun,
};
