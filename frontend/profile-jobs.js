import ProfileJobs from "./Profile/ProfileJobs.svelte";
import { mount } from "svelte";

const app = mount(ProfileJobs, {
    target: document.querySelector("#jobsContainer"),
    props: {}
});
