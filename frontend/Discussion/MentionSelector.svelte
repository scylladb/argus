<script>
    import { createEventDispatcher, onMount } from "svelte";
    import Select from "svelte-select";
    import Fa from "svelte-fa";
    import { faTimes } from "@fortawesome/free-solid-svg-icons";
    import User from "../Profile/User.svelte";
    import { filterUser } from "../Common/SelectUtils";
    export let users = {};
    let select;
    const dispatch = createEventDispatcher();
    const prepareUsers = function (users) {
        return Object.values(users)
            .map((val) => {
                return {
                    label: val.username,
                    value: val.id,
                    picture_id: val.picture_id,
                    full_name: val.full_name,
                };
            })
            .sort((a, b) => {
                if (a.value > b.value) {
                    return 1;
                } else if (b.value > a.value) {
                    return -1;
                }
                return 0;
            });
    };

    const handleMention = function (e) {
        dispatch("mentionUser", users[e.detail.value]);
    };

    const handleKeypress = function(e) {
        if (e.code && e.code == "Escape") {
            dispatch("closeMention");
        }
    }

    onMount(() => {
        select.querySelector("input").focus();
    });
</script>

<div
    class="mention-select bg-lighter p-1 rounded shadow d-flex align-items-center"
    bind:this={select}
    on:keydown={handleKeypress}
>
    <div class="flex-fill">
        <Select
            Item={User}
            items={prepareUsers(users)}
            itemFilter={filterUser}
            placeholder="@..."
            on:select={handleMention}
        />
    </div>
    <button
        class="ms-1 btn btn-dark"
        on:click={(e) => {
            e.stopPropagation();
            dispatch("closeMention");
        }}
    >
        <Fa icon={faTimes} />
    </button>
</div>

<style>
    .mention-select {
        min-width: 256px;
        max-width: 384px;
    }

    .mention-select:hover {
        color: black;
    }
</style>
