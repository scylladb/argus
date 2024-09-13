import ReleasePlanner from "./ReleasePlanner/ReleasePlanner.svelte";

console.log("Release Planner Init");
const RELEASE_DATA = window.releaseData;

const app = new ReleasePlanner({
    target: document.querySelector("div#releasePlanner"),
    props: {
        release: RELEASE_DATA.release,
        plans: RELEASE_DATA.plans,
    }
});
