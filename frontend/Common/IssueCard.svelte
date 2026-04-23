<script module lang="ts">
    import GithubIssue from "../Github/GithubIssue.svelte";
    import JiraIssue from "../Jira/JiraIssue.svelte";
    import UnknownIssue from "./UnknownIssue.svelte";

    export const IssueComponents: Record<string, any> = {
        github: GithubIssue,
        jira: JiraIssue,
        unknown: UnknownIssue,
    };
</script>

<script lang="ts">
    import type { Issue } from "./IssueTypes";

    interface Props {
        issue: Issue;
        [key: string]: any;
    }

    let { issue, ...rest }: Props = $props();
    const Component = IssueComponents[issue?.subtype] ?? IssueComponents.unknown;
</script>

<Component {issue} {...rest} />
