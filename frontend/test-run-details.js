import TestRun from "./TestRun/TestRun.svelte";

const app = new TestRun({
    target: document.querySelector("div#testRunBody"),
    props: {
        id: test_run_id
    }
});
