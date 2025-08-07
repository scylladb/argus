import TeamManager from "./Teams/TeamManager.svelte";
import { mount } from "svelte";

const app = mount(TeamManager, {
    target: document.querySelector("#teamsContainer")
});
