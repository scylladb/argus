import HealthIndicator from "./Common/HealthIndicator.svelte";
import { mount } from "svelte";

const target = document.querySelector("#healthIndicator");

if (target) {
    mount(HealthIndicator, { target, props: {} });
}
