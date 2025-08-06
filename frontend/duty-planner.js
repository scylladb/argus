import DutyPlanner from "./ReleasePlanner/DutyPlanner.svelte";
import { mount } from "svelte";

const dutyPlanner = mount(DutyPlanner, {
    target: document.querySelector("div#dutyPlanner"),
    props: {
        releaseData: releaseData
    }
});
