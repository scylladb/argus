import { element } from "svelte/internal";
import ViewUserResolver from "./Profile/ViewUserResolver.svelte";
import { mount } from "svelte";

document.querySelectorAll("span.view-creator").forEach(elem => {
    const app = mount(ViewUserResolver, {
            target: elem,
            props: {
                element: elem,
            }
        });
});
