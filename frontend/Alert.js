import AlertWidget from "./Alerts/AlertWidget.svelte";
import { mount } from "svelte";

document.addEventListener("DOMContentLoaded", () => {
    const alertApp = mount(AlertWidget, {
            target: document.querySelector("#argusErrors"),
            props: {
                flashes: globalFlashes
            }
        });
})
