import ProfileSchedules from "./Profile/ProfileSchedules.svelte";
import { mount } from "svelte";

const app = mount(ProfileSchedules, {
    target: document.querySelector("#scheduleContainer"),
    props: {
        schedules: globalSchedules
    }
});
