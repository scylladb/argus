import ReleaseScheduler from "./ReleasePlanner/ReleaseScheduler.svelte";

const releaseDashboard = new ReleaseScheduler({
    target: document.querySelector("div#releaseScheduler"),
    props: {
        releaseData: releaseData
    }
});
