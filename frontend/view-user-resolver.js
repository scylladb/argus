import { element } from "svelte/internal";
import ViewUserResolver from "./Profile/ViewUserResolver.svelte";

document.querySelectorAll("span.view-creator").forEach(elem => {
    const app = new ViewUserResolver({
        target: elem,
        props: {
            element: elem,
        }
    });
});
