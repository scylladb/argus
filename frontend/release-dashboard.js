import ReleaseDashboard from "./ReleaseDashboard/ReleaseDashboard.svelte";
import { mount } from "svelte";

const releaseDashboard = mount(ReleaseDashboard, {
    target: document.querySelector("div#releaseDashboard"),
    props: {
        releaseData: releaseData
    }
});
