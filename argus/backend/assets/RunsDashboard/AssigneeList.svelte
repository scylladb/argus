<script>
    import { userList } from "./UserlistSubscriber";
    export let assignees = [];
    let users = {};
    $: users = $userList;

    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/static/no-user-picture.png";
    };
</script>

{#if Object.keys(users).length > 0}
    <div class="d-flex">
        {#each assignees as assignee}
            <div title={users[assignee].full_name} class="assignee-container">
                <img
                    src={getPicture(users[assignee].picture_id)}
                    class="img-tiny"
                    alt="{users[assignee].full_name}"
                />
            </div>
        {/each}
    </div>
{/if}

<style>
    .img-tiny {
        width: 24px;
        cursor: help;
        border-radius: 50%;
        border: solid 1px rgb(122, 122, 122);
    }

    .assignee-container:not(:first-child) {
        margin-left: -8px;
    }
</style>
