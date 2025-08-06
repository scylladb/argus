import ReleasePlanner from "./ReleasePlanner/ReleasePlanner.svelte";
import { mount } from "svelte";

console.log("Release Planner Init");
const RELEASE_DATA = window.releaseData;

const app = mount(ReleasePlanner, {
    target: document.querySelector("div#releasePlanner"),
    props: {
        release: RELEASE_DATA.release,
        plans: RELEASE_DATA.plans,
    }
});
