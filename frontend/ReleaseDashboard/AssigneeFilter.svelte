<script lang="ts">
    import { run } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { filterUser } from "../Common/SelectUtils";
    let { user } = $props();
    const dispatch = createEventDispatcher();
    let users = $state({});
    run(() => {
        users = $userList;
    });

    const handleFilter = function(e) {
        dispatch("selected", e.detail);
    };

    const handleClear = function(e) {
        dispatch("selected", undefined);
    };
</script>

<div class="w-100">
    <Select
        --item-height="auto"
        --item-line-height="auto"
        value={user}
        itemFilter={filterUser}
        placeholder="Filter..."
        label="username"
        itemId="id"
        items={Object.values(users)}
        hideEmptyState={true}
        clearable={true}
        searchable={true}
        on:select={handleFilter}
        on:clear={handleClear}
    >
        <div slot="item" let:item let:index>
            <User {item} />
        </div>
    </Select>
</div>
