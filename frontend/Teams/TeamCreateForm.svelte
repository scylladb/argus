<script lang="ts">
    import { run } from 'svelte/legacy';

    import { faPlusSquare } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import Select from "svelte-select";
    import { applicationCurrentUser } from "../argus";
    import type { User as IUser, Users } from "../Common/UserTypes";
    import User from "../Profile/User.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import { createUserSelectList, TeamManagerAPIError, TeamManagerException, TeamRoutes, type RawTeamCreateResponse, type UserSelectItem } from "./TeamUtils";
    const dispatch = createEventDispatcher();
    let currentUser: IUser = applicationCurrentUser;
    let users: Users = $state($userList);
    run(() => {
        users = $userList;
    });
    let selectedUsers: UserSelectItem[] | undefined = $state();
    let newTeamName: string = $state();

    const handleSubmitNewTeam = async function() {
        if (!newTeamName) {
            sendMessage("error", "Team name cannot be empty!", "TeamCreateForm::handleSubmitNewTeam");
            return;
        }
        if (!selectedUsers) {
            sendMessage("error", "No members selected", "TeamCreateForm::handleSubmitNewTeam");
            return;
        }
        let members = selectedUsers.map(u => u.user_id);
        try {
            const response = await fetch(TeamRoutes.CREATE_TEAM, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    name: newTeamName,
                    leader: currentUser.id,
                    members: members
                }),
            });
            if (!response.ok) {
                throw new TeamManagerException(`API Transport Error ${response.status}`);
            }
            const json: RawTeamCreateResponse = await response.json();
            if (json.status === "ok") {
                sendMessage("success", "Team created!", "TeamCreateForm::handleSubmitNewTeam");
                dispatch("teamCreated", json);
                newTeamName = "";
                selectedUsers = undefined;
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (err) {
            if (err instanceof TeamManagerAPIError) {
                sendMessage("error", `Failed to create a team!\nAPI Error: ${err.exception}`, "TeamCreateForm::handleSubmitNewTeam");
                return;
            }
            console.log(err);
        }
    };
</script>

<button
class="btn btn-sm btn-primary"
data-bs-toggle="collapse"
data-bs-target="#createTeamCollapse"
>
    <Fa icon={faPlusSquare} /> New Team
</button>
<div id="createTeamCollapse" class="collapse">
{#if Object.keys(users).length > 0}
    <div>
        <label class="form-label" for="teamName">Name</label>
        <input class="form-control" type="text" id="teamName" bind:value={newTeamName}>
    </div>
    <div class="mb-2">
        <label class="form-label" for="teamName">Members</label>
        <Select
            --item-height="auto"
            --item-line-height="auto"
            items={createUserSelectList(Object.values(users), currentUser)}
            multiple={true}
            placeholder="Members"
            bind:value={selectedUsers}
            on:select={() => { console.log(selectedUsers); }}
        >
            <div slot="item" let:item let:index>
                <User {item} />
            </div>
        </Select>
    </div>
    <div>
        <button class="btn btn-success btn-sm" onclick={handleSubmitNewTeam}>Create</button>
    </div>
{:else}
    Fetching users...
{/if}
</div>
