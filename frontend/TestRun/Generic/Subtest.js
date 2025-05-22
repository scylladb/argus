import { PytestTab, PytestRun } from "../Pytest";

export const Cases = {
    PYTEST: "pytest",
};

export const Tabs = {
    [Cases.PYTEST]: PytestTab,
};

export const TabBody = {
    [Cases.PYTEST]: PytestRun,
};
