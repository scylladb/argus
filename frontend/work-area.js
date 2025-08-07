import WorkArea from "./WorkArea/WorkArea.svelte";
import { mount } from "svelte";

const app = mount(WorkArea, {
    target: document.querySelector("div#dashboard-body"),
    props: {
    }
});
