import TestRun from "./TestRun/TestRun.svelte";
import { mount } from "svelte";

const app = mount(TestRun, {
    target: document.querySelector("div#testRunBody"),
    props: {
        runId: test_run_id,
        tab: gTab
    }
});
