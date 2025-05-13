import ReleasePlan from "./ReleasePlanner/ReleasePlan.svelte";

const app = new ReleasePlan({
    target: document.querySelector("div#planDashboard"),
    props: {
        plan: globalThis.ARGUS_PLAN_DATA,
        detached: true,
        expandedPlans: { [globalThis.ARGUS_PLAN_DATA.id]: true }
    }
});
