<script>
    import {userList} from "../Stores/UserlistSubscriber";
    import User from "../Profile/User.svelte";
    import Select from "svelte-select";
    import {filterUser} from "../Common/SelectUtils";
    import UserSelection from "../Profile/UserSelection.svelte";

    export let assignee_id;
    export let disabled = false;
    let users = {};
    $: users = $userList;
    let currentAssignee = $userList[assignee_id];
    let selectedAssignee = {
        label: currentAssignee?.username,
        value: currentAssignee?.id,
        picture_id: currentAssignee?.picture_id,
        full_name: currentAssignee?.full_name
    };
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

</script>

<Select
        Item={User}
        Selection={UserSelection}
        items={prepareUsers(users)}
        value={selectedAssignee}
        itemFilter={filterUser}
        placeholder="@..."
        on:select
        on:clear
        isDisabled={disabled}
/>
