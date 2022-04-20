import AdminPanel from "./AdminPanel/AdminPanel.svelte";

const applicationCurrentRoute = gCurrentRoute ?? "index";

const app = new AdminPanel({
    target: document.querySelector("div#adminPanel"),
    props: {
        currentRoute: applicationCurrentRoute,
    }
});
