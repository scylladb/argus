import queryString from "query-string";
import { stateEncoder } from "../Common/StateManagement";

export class WorkAreaState {
    testRuns: string[] = $state([]);
    additionalRuns: Record<string, string[]> = $state({});

    pushUrl = (): void => {
        const params = queryString.parse(document.location.search, { arrayFormat: "bracket" });
        params.state = stateEncoder(this.testRuns);
        history.pushState({}, "", `?${queryString.stringify(params, { arrayFormat: "bracket" })}`);
    };

    openTests = (testIds: string[]): void => {
        const added = testIds.filter((id) => !this.testRuns.includes(id));
        if (added.length === 0) return;
        this.testRuns.push(...added);
        this.pushUrl();
    };

    openTest = (testId: string): void => this.openTests([testId]);

    removeTest = (testId: string): void => {
        this.testRuns = this.testRuns.filter((id) => id !== testId);
        delete this.additionalRuns[testId];
        this.pushUrl();
    };

    toggleTest = (testId: string): void => {
        if (this.testRuns.includes(testId)) {
            this.removeTest(testId);
        } else {
            this.openTest(testId);
        }
    };

    openRun = (testId: string, runId: string): void => {
        const runs = this.additionalRuns[testId] ?? [];
        if (!runs.includes(runId)) this.additionalRuns[testId] = [...runs, runId];
        this.openTest(testId);
    };

    closeRun = (testId: string, runId: string): void => {
        const remaining = (this.additionalRuns[testId] ?? []).filter((id) => id !== runId);
        if (remaining.length === 0) {
            this.removeTest(testId);
        } else {
            this.additionalRuns[testId] = remaining;
        }
    };
}
