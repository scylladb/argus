<script>
    import { createEventDispatcher } from "svelte";
    import Select from "svelte-select";
    import { getPicture } from "../Common/UserUtils";
    import User from "../Profile/User.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { filterUser } from "../Common/SelectUtils";

    import { userList } from "../Stores/UserlistSubscriber";
    export let testRun;
    const dispatch = createEventDispatcher();

    let userSelect = {};
    let users = {};

    $: users = $userList;
    $: userSelect = createUserSelectCollection(users);

    const createUserSelectCollection = function (users) {
        const dummyUser = {
            value: "unassigned",
            label: "unassigned",
            picture_id: undefined,
            full_name: "Unassigned",
            user_id: "none-none-none",
        };

        userSelect = Object.values(users).map((user) => {
            return {
                value: user.username,
                label: user.username,
                picture_id: user.picture_id,
                full_name: user.full_name,
                user_id: user.id,
            };
        });

        return [dummyUser, ...userSelect].reduce((acc, val) => {
            acc[val.user_id] = val;
            return acc;
        }, {});
    };

    const findAssignee = function (run, userSelect) {
        const placeholder = {
            value: "unassigned",
            id: "none-none-none",
        };
        if (Object.values(userSelect).length < 2) return;
        if (!run) {
            return placeholder;
        }
        if (run.assignee) {
            let user = userSelect[run.assignee];
            if (!user) {
                return placeholder;
            }
            return {
                id: user.user_id,
                value: user.value,
            };
        }
        return placeholder;
    };

    let currentAssignee = "unassigned";
    $: currentAssignee = findAssignee(testRun, userSelect);


    const handleAssign = async function (event) {
        let new_assignee = event.detail.value;
        new_assignee = Object.values(userSelect).find(
            (user) => user.value == new_assignee
        );
        if (!new_assignee) {
            return;
        }

        new_assignee = new_assignee.user_id;
        try {
            let apiResponse = await fetch(`/api/v1/test/${testRun.test_id}/run/${testRun.id}/assignee/set`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    assignee: new_assignee,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                dispatch("assigneeUpdate", { assignee: new_assignee });
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error assigning person to the test run.\nMessage: ${error.response.arguments[0]}`,
                    "RunAssigneeSelector::handleAssign"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during assignment call",
                    "RunAssigneeSelector::handleAssign"
                );
            }
        }
    };

</script>

<div class="row mb-2 text-sm justify-content-end">
    <div class="col-6">
        {#if Object.keys(userSelect).length > 1}
            <div class="text-muted text-sm text-end mb-2">
                Assignee
            </div>
            <div class="border rounded">
                <div class="d-flex align-items-center m-1">
                    {#if users[currentAssignee.id]}
                        <img
                            class="img-profile me-2"
                            src={getPicture(
                                users[currentAssignee.id]
                                    ?.picture_id
                            )}
                            alt={users[currentAssignee.id]
                                ?.username}
                        />
                    {/if}
                    <div class="flex-fill">
                        <Select
                            itemFilter={filterUser}
                            Item={User}
                            value={currentAssignee.value}
                            items={Object.values(
                                userSelect
                            )}
                            hideEmptyState={true}
                            isClearable={false}
                            isSearchable={true}
                            on:select={handleAssign}
                        />
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
<style>
    .img-profile {
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
    }
</style>
