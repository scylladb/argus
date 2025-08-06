import queryString from "query-string";
import ViewDashboard from "./Views/ViewDashboard.svelte";
import { mount } from "svelte";

const app = mount(ViewDashboard, {
    target: document.querySelector("div#viewDashboard"),
    props: {
        view: globalThis.ARGUS_VIEW_DATA,
        productVersion: queryString.parse(document.location.search)?.productVersion,
    }
});
