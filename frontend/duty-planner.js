import DutyPlanner from "./ReleasePlanner/DutyPlanner.svelte";

const dutyPlanner = new DutyPlanner({
    target: document.querySelector("div#dutyPlanner"),
    props: {
        releaseData: releaseData
    }
});
