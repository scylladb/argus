import ReleaseDashboard from "./ReleaseDashboard/ReleaseDashboard.svelte";

const releaseDashboard = new ReleaseDashboard({
    target: document.querySelector("div#releaseDashboard"),
    props: {
        releaseData: releaseData
    }
});
