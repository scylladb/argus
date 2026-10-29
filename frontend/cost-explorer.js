import CostExplorer from "./CostExplorer/CostExplorer.svelte";
import { mount } from "svelte";

const app = mount(CostExplorer, {
    target: document.querySelector("div#costExplorer"),
});
