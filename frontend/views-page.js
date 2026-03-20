import Views from "./Views/Views.svelte"
import { mount } from "svelte";

const app = mount(Views, {
    target: document.querySelector("div#viewContainer"),
    props: {
        views: globalThis.ARGUS_VIEWS,
    }
});
