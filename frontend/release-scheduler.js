import ReleaseScheduler from "./ReleasePlanner/ReleaseScheduler.svelte";
import { mount } from "svelte";

const releaseDashboard = mount(ReleaseScheduler, {
    target: document.querySelector("div#releaseScheduler"),
    props: {
        releaseData: releaseData
    }
});
