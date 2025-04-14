import TestRun from "./TestRun/TestRun.svelte";

const app = new TestRun({
    target: document.querySelector("div#testRunBody"),
    props: {
        runId: test_run_id,
        tab: gTab
    }
});
