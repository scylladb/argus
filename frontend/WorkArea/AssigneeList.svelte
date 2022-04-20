<script>
    import { userList } from "../Stores/UserlistSubscriber";
    export let assignees = [];
    export let smallImage = false;
    let users = {};
    $: users = $userList;

    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
    };
</script>

{#if Object.keys(users).length > 0}
    <div class="d-flex">
        {#each assignees as assignee}
            <div title={users[assignee].full_name} class="assignee-container">
                <div
                    src={getPicture(users[assignee]?.picture_id)}
                    class="img-tiny"
                    class:img-smaller={smallImage}
                    alt="{users[assignee].full_name}"
                    style="background-image: url({getPicture(users[assignee].picture_id)});"
                />
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
