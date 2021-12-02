import FlashDebugComponent from "./FlashDebugComponent.svelte"

document.addEventListener("DOMContentLoaded", () => {
    const flashDebugComponent = new FlashDebugComponent({
        target: document.querySelector("#flashDebug"),
        props: {}
    })
});
