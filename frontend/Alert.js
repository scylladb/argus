import AlertWidget from "./Alerts/AlertWidget.svelte";

document.addEventListener("DOMContentLoaded", () => {
    const alertApp = new AlertWidget({
        target: document.querySelector("#argusErrors"),
        props: {
            flashes: globalFlashes
        }
    });
})
