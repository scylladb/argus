import ProfileSchedules from "./Profile/ProfileSchedules.svelte";

const app = new ProfileSchedules({
    target: document.querySelector("#scheduleContainer"),
    props: {
        schedules: globalSchedules
    }
});
