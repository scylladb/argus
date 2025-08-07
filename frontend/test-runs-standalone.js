import TestRuns from "./WorkArea/TestRuns.svelte";
import { mount } from "svelte";

const app = mount(TestRuns, {
    target: document.querySelector("div#testRunBody"),
    props: {
        testId: gTestId,
        additionalRuns: additionalRuns
    }
});
