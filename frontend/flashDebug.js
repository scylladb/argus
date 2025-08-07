import FlashDebugComponent from "./Debug/FlashDebugComponent.svelte"
import { mount } from "svelte";

document.addEventListener("DOMContentLoaded", () => {
    const flashDebugComponent = mount(FlashDebugComponent, {
            target: document.querySelector("#flashDebug"),
            props: {}
        })
});
