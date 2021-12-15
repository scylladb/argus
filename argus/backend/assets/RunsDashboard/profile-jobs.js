import ProfileJobs from "./ProfileJobs.svelte";

const app = new ProfileJobs({
    target: document.querySelector("#jobsContainer"),
    props: {
        runs: globalRuns
    }
});
