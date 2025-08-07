<script lang="ts">
    import { run } from 'svelte/legacy';

    import { getUser, getPicture } from "../Common/UserUtils";
    import { userList } from "../Stores/UserlistSubscriber";
    interface Props {
        assignees?: any;
        smallImage?: boolean;
    }

    let { assignees = [], smallImage = false }: Props = $props();
    let users = $state({});
    run(() => {
        users = $userList;
    });
</script>

{#if Object.keys(users).length > 0}
    <div class="d-flex">
        {#each assignees as assignee}
            <div title={getUser(assignee, users).full_name} class="assignee-container">
                <div
                    src={getPicture(getUser(assignee, users).picture_id)}
                    class="img-tiny"
                    class:img-smaller={smallImage}
                    alt="{getUser(assignee, users).full_name}"
                    style="background-image: url({getPicture(getUser(assignee, users).picture_id)});"
></div>
            </div>
        {/each}
    </div>
{/if}

<style>
    .img-tiny {
        height: 24px;
        width: 24px;
        background-color: black;
        background-clip: border-box;
        background-repeat: no-repeat;
        background-position: center;
        background-size: cover;
        image-rendering: crisp-edges;
        cursor: help;
        border-radius: 50%;
        /* border: solid 1px rgb(122, 122, 122); */
    }

    .img-smaller {
        height: 20px;
        width: 20px;
    }

    .assignee-container:not(:first-child) {
        margin-left: -8px;
    }
</style>
