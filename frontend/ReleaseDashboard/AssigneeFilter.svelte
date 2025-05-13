<script>
    import { createEventDispatcher } from "svelte";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { filterUser } from "../Common/SelectUtils";

    const dispatch = createEventDispatcher();
    let users = {};
    $: users = $userList;

    const handleFilter = function(e) {
        dispatch("selected", e.detail);
    };
</script>

<div class="w-100">
    <Select
        itemFilter={filterUser}
        placeholder="Filter..."
        labelIdentifier="username"
        optionIdentifier="id"
        Item={User}
        items={Object.values(users)}
        hideEmptyState={true}
        isClearable={true}
        isSearchable={true}
        on:select={handleFilter}
        on:clear={handleFilter}
    />
</div>
