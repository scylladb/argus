<script lang="ts">
    import { getUser, getPicture } from "../../../Common/UserUtils";
    import { userList } from "../../../Stores/UserlistSubscriber";
    import type { TestRun } from "./Interfaces";

    export let run: TestRun;

    let users = {};
    $: users = $userList;

    const assignee = run.assignee;
    $: user = assignee && assignee !== "Unassigned" ? getUser(assignee, users) : null;
    $: pictureUrl = user ? getPicture(user.picture_id) : "";
</script>

{#if !assignee || assignee === "Unassigned"}
    <span class="text-muted">Unassigned</span>
{:else}
    <div class="d-flex align-items-center" title={user ? (user.full_name || user.username || assignee) : ""}>
        <div class="img-profile me-2" style="background-image: url({pictureUrl});"></div>
    </div>
{/if}

<style>
    .img-profile {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        flex-shrink: 0;
    }
</style>
