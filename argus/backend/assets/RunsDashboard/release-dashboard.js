import ReleaseDashboard from "./ReleaseDashboard.svelte";

const releaseDashboard = new ReleaseDashboard({
    target: document.querySelector("div#releaseDashboard"),
    props: {
        releaseData: releaseData
    }
});