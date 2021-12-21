<script>
    import Fa from "svelte-fa";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import { faCheckCircle } from "@fortawesome/free-regular-svg-icons";
    import { faExclamationCircle, faExternalLinkSquareAlt } from "@fortawesome/free-solid-svg-icons";
    import { userList } from "../Stores/UserlistSubscriber";
    let users = {};
    $: users = $userList;
    const IssueColorMap = {
        "open": "text-success",
        "closed": "text-danger"
    };

    const IssueIcon = {
        "open": faExclamationCircle,
        "closed": faCheckCircle
    }
    export let issue = {
        group_id: "",
        id: "",
        issue_number: -1,
        last_status: "unknown",
        owner: "nobody",
        release_id: "",
        repo: "no-repo",
        run_id: "",
        test_id: "",
        title: "NO ISSUE",
        type: "issues",
        url: "https://github.com/",
        user_id: "",
        added_on: "Mon, 1 Jan 1970 9:00:00 GMT",
    };
</script>

<div class="row m-2 border rounded p-2">
    <div class="col hstack">
        <div class="me-2 text-truncate" style="width: 20em;" title="{issue.title}"><Fa icon={faGithub}/> <a href="{issue.url}">{issue.title}</a></div>
        <div class="text-muted me-auto">{issue.repo}#{issue.issue_number}</div>
        {#if Object.keys(users).length > 0}
            <div class="text-muted me-2" title={new Date(issue.added_on).toISOString()}>Added by {users[issue.user_id].username}</div>
        {/if}
        <div class="text-muted"><a class="link-secondary" href="/test_run/{issue.run_id}">Run<Fa icon={faExternalLinkSquareAlt}/></a></div>
    </div>
</div>
