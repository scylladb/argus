import WorkArea from "./WorkArea/WorkArea.svelte";

const app = new WorkArea({
    target: document.querySelector("div#dashboard-body"),
    props: {
    }
});
