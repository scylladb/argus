import queryString from "query-string";
import ViewDashboard from "./Views/ViewDashboard.svelte";

const app = new ViewDashboard({
    target: document.querySelector("div#viewDashboard"),
    props: {
        view: globalThis.ARGUS_VIEW_DATA,
        productVersion: queryString.parse(document.location.search)?.productVersion,
    }
});
