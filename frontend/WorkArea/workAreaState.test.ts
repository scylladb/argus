import { describe, it, expect, beforeEach } from "vitest";
import { stateDecoder } from "../Common/StateManagement";
import { WorkAreaState } from "./workAreaState.svelte";

beforeEach(() => {
    history.replaceState({}, "", "/workspace");
});

describe("WorkAreaState", () => {
    it("opens tests once and records them in the URL", () => {
        const work = new WorkAreaState();

        work.openTests(["t1", "t2"]);
        work.openTest("t1");

        expect(work.testRuns).toEqual(["t1", "t2"]);
        expect(stateDecoder()).toEqual(["t1", "t2"]);
    });

    it("toggles a test", () => {
        const work = new WorkAreaState();

        work.toggleTest("t1");
        work.toggleTest("t1");

        expect(work.testRuns).toEqual([]);
        expect(stateDecoder()).toEqual([]);
    });

    it("opens the test of a run and keeps every run picked into it", () => {
        const work = new WorkAreaState();

        work.openRun("t1", "r1");
        work.openRun("t1", "r2");
        work.openRun("t1", "r2");

        expect(work.testRuns).toEqual(["t1"]);
        expect(work.additionalRuns).toEqual({ t1: ["r1", "r2"] });
    });

    it("closes a run and closes the test with its last run", () => {
        const work = new WorkAreaState();
        work.openRun("t1", "r1");
        work.openRun("t1", "r2");

        work.closeRun("t1", "r1");
        expect(work.testRuns).toEqual(["t1"]);
        expect(work.additionalRuns).toEqual({ t1: ["r2"] });

        work.closeRun("t1", "r2");
        expect(work.testRuns).toEqual([]);
        expect(stateDecoder()).toEqual([]);
    });

    it("drops the runs of a closed test", () => {
        const work = new WorkAreaState();
        work.openRun("t1", "r1");

        work.removeTest("t1");
        work.openTest("t1");

        expect(work.additionalRuns).toEqual({});
    });
});
