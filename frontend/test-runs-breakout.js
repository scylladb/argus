import TestRunsPanel from "./WorkArea/TestRunsPanel.svelte";
import { Base64 } from "js-base64";

let params = new URLSearchParams(document.location.search);
let state = params.get("state");
let decodedState = state ? Base64.decode(state) : "{}";


const app = new TestRunsPanel({
    target: document.querySelector("div#testRunsBreakout"),
    props: {
        testRuns: JSON.parse(decodedState)
    }
});
