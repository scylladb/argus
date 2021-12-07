import ReleaseScheduler from "./ReleaseScheduler.svelte";

const releaseDashboard = new ReleaseScheduler({
    target: document.querySelector("div#releaseScheduler"),
    props: {
        releaseData: releaseData
    }
});
