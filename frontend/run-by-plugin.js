import TestRuns from "./WorkArea/TestRuns.svelte";

const app = new TestRuns({
    target: document.querySelector("div#testRunBody"),
    props: {
        testId: gTestId,
        additionalRuns: gRun,
        tab: gTab
    }
});
