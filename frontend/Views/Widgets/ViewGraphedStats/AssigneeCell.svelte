<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import { getUser, getPicture } from "../../../Common/UserUtils";
    import { userList } from "../../../Stores/UserlistSubscriber";
    import type { TestRun } from "./Interfaces";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    let users = $state({});
    run_1(() => {
        users = $userList;
    });

    const assignee = run.assignee;
    let user = $derived(assignee && assignee !== "Unassigned" ? getUser(assignee, users) : null);
    let pictureUrl = $derived(user ? getPicture(user.picture_id) : "");
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
