<script lang="ts">
    import Fa from "svelte-fa";
    import { faGithub, faJira } from "@fortawesome/free-brands-svg-icons";
    import { getTitle, getUrl, getKey } from "./IssueTypes";
    import type { Issue } from "./IssueTypes";

    interface Props {
        issue: Issue;
    }

    let { issue }: Props = $props();

    const url = $derived(getUrl(issue));
    const title = $derived(getTitle(issue));
    const key = $derived(getKey(issue));
    const icon = $derived(issue.subtype === "jira" ? faJira : faGithub);
</script>

<div class="d-flex align-items-center">
    <div class:jira-icon={issue.subtype === "jira"}>
        <Fa {icon} />
    </div>
    <div class="ms-1">
        <a target="_blank" href={url}>
            {title}
        </a>
    </div>
    <div class="ms-auto ps-1 text-muted issue-key">
        {key}
    </div>
</div>

<style>
    .issue-key {
        font-size: 0.85em;
        white-space: nowrap;
    }

    .jira-icon {
        color: #2684ff;
    }
</style>
