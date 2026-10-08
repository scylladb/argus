import IssueLinks from "./IssueLinks/IssueLinks.svelte";
import { mount } from "svelte";

const app = mount(IssueLinks, {
    target: document.querySelector("div#issueLinks"),
    props: {
        issueKey: gIssueKey,
    },
});
