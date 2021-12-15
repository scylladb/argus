import ProfileSchedules from "./ProfileSchedules.svelte";

const app = new ProfileSchedules({
    target: document.querySelector("#scheduleContainer"),
    props: {
        schedules: globalSchedules
    }
});
