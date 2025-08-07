import ReleasePlan from "./ReleasePlanner/ReleasePlan.svelte";
import { mount } from "svelte";

const app = mount(ReleasePlan, {
    target: document.querySelector("div#planDashboard"),
    props: {
        plan: globalThis.ARGUS_PLAN_DATA,
        detached: true,
        expandedPlans: { [globalThis.ARGUS_PLAN_DATA.id]: true }
    }
});
