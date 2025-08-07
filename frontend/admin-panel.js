import AdminPanel from "./AdminPanel/AdminPanel.svelte";
import { mount } from "svelte";

const applicationCurrentRoute = gCurrentRoute ?? "index";

const app = mount(AdminPanel, {
    target: document.querySelector("div#adminPanel"),
    props: {
        currentRoute: applicationCurrentRoute,
    }
});
