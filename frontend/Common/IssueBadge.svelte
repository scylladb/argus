<!--
    Shared inline issue icon + label renderer.
    Works with the `type`-based discriminator ("github" | "jira") used by
    graphed_stats and sct/service endpoints.

    Renders: [icon] [label text]
    where icon is faJira / faGithub (or state-based for GitHub),
    and label is the Jira key or GitHub #number.
-->
<script lang="ts">
    import Fa from "svelte-fa";
    import { faCheckCircle, faDotCircle } from "@fortawesome/free-solid-svg-icons";
    import { faGithub, faJira } from "@fortawesome/free-brands-svg-icons";
    import { isJiraIssue, getIssueLabel } from "./IssueUtils";

    interface Props {
        issue: any;
        /** Show state-based icons for GitHub (faDotCircle/faCheckCircle) instead of faGithub brand icon */
        stateIcons?: boolean;
        /** Render only the icon, no label text */
        iconOnly?: boolean;
    }

    let { issue, stateIcons = false, iconOnly = false }: Props = $props();

    function getIcon(issue: any) {
        if (isJiraIssue(issue)) return faJira;
        if (stateIcons) {
            return issue.state === "open" ? faDotCircle : faCheckCircle;
        }
        return faGithub;
    }
</script>

<Fa icon={getIcon(issue)} color={isJiraIssue(issue) ? "#0052CC" : undefined} />{#if !iconOnly}{" "}{getIssueLabel(issue)}{/if}
