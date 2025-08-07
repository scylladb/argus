<script lang="ts">
    import { run } from 'svelte/legacy';

    import { faCalendar, faEdit, faSave, faTimes, faUserPlus } from "@fortawesome/free-solid-svg-icons";
    import { marked as parse } from "marked";
    import DOMPurify from "dompurify";
    import format from "string-template";
    import Fa from "svelte-fa";
    import { applicationCurrentUser } from "../argus";
    import type { Users, User as IUser } from "../Common/UserTypes";
    import { getUser, getPicture } from "../Common/UserUtils";
    import { markdownRendererOptions } from "../markdownOptions";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import TeamMember from "./TeamMember.svelte";
    import { createUserSelectList, TeamManagerAPIError, TeamRoutes, type RawTeamMotdUpdateResponse, type RawTeamUpdateResponse, type Team, type UserSelectItem } from "./TeamUtils";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { createEventDispatcher } from "svelte";

    interface Props {
        team: Team;
    }

    let { team = $bindable() }: Props = $props();
    const dispatch = createEventDispatcher();
    let currentUser: IUser = applicationCurrentUser;
    let users: Users = $state();
    run(() => {
        users = $userList;
    });
    let newMotdText = $state(team.motd);
    let newName = $state(team.name);
    let editingName = $state(false);
    let newMembers: UserSelectItem[] | undefined = $state();

    const resolveUsers = function(members: string[], users: Users): IUser[] {
        return members.map((memberId) => {
            return getUser(memberId, users);
        });
    };

    const handleUpdateMotd = async function() {
        try {
            const response = await fetch(format(TeamRoutes.UPDATE_MOTD_FOR_TEAM, {teamId: team.id}), {
                method: "POST",
                body: JSON.stringify({
                    id: team.id,
                    motd: newMotdText,
                }),
                headers: {
                    "Content-Type": "application/json"
                }
            });
            const json: RawTeamMotdUpdateResponse = await response.json();
            if (json.status == "ok") {
                team.motd = newMotdText;
                dispatch("teamUpdated", team);
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (error) {
            if (error instanceof TeamManagerAPIError)
            {
                sendMessage("error", `${error.arguments[0]}`, "TeamDetail::handleUpdateMotd");
            }
            console.log(error);
        } finally {
            newMotdText = team.motd;
        }
    };

    const handleUpdateMembers = async function() {
        if (!newMembers) return;
        try {
            const response = await fetch(format(TeamRoutes.UPDATE_TEAM, {teamId: team.id}), {
                method: "POST",
                body: JSON.stringify({
                    id: team.id,
                    members: newMembers.map((i) => i.user_id),
                    name: team.name,
                }),
                headers: {
                    "Content-Type": "application/json"
                }
            });
            const json: RawTeamUpdateResponse = await response.json();
            if (json.status == "ok") {
                team = json.response.team;
                dispatch("teamUpdated", team);
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (error) {
            if (error instanceof TeamManagerAPIError)
            {
                sendMessage("error", `${error.arguments[0]}`, "TeamDetail::handleUpdateMembers");
            }
            console.log(error);
        }
    };

    const handleUpdateTeamName = async function() {
        if (!newName) {
            sendMessage("error", "Name cannot be empty", "TeamDetail::handleUpdateTeamName");
            newName = team.name;
            return;
        }
        try {
            const response = await fetch(format(TeamRoutes.UPDATE_TEAM, {teamId: team.id}), {
                method: "POST",
                body: JSON.stringify({
                    id: team.id,
                    members: team.members,
                    name: newName,
                }),
                headers: {
                    "Content-Type": "application/json"
                }
            });
            const json: RawTeamUpdateResponse = await response.json();
            if (json.status == "ok") {
                team = json.response.team;
                dispatch("teamUpdated", team);
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (error) {
            if (error instanceof TeamManagerAPIError)
            {
                sendMessage("error", `${error.arguments[0]}`, "TeamDetail::handleUpdateTeamName");
            }
            console.log(error);
        } finally {
            editingName = false;
        }
    };
</script>

<div class="my-2">
    <h2 class="border-bottom py-2 mb-2 d-flex">
        {#if editingName}
            <div class="d-flex">
                <input type="text" bind:value={newName}>
                <button class="ms-2 btn btn-sm btn-success" onclick={handleUpdateTeamName}><Fa icon={faSave}/></button>
                <button class="ms-2 btn btn-sm btn-secondary" onclick={() => (editingName = false)}><Fa icon={faTimes}/></button>
            </div>
        {:else}
            <div class="d-flex">
                <div>{team.name}</div>
                {#if currentUser.id == team.leader}
                    <button class="ms-2 btn btn-sm btn-primary" onclick={() => (editingName = true)}><Fa icon={faEdit}/></button>
                {/if}
            </div>
        {/if}
        {#if team.leader == currentUser.id}
            <div class="ms-auto">
                <button class="btn btn-sm btn-primary" data-bs-toggle="modal" data-bs-target="#modalMotdUpdate-{team.id}">
                    <Fa icon={faCalendar}/> Edit MOTD
                </button>
            </div>
            <div class="ms-2">
                <button
                    class="btn btn-sm btn-primary"
                    data-bs-toggle="modal"
                    data-bs-target="#modalEditMembers-{team.id}"
                    onclick={() => newMembers = createUserSelectList(resolveUsers(team.members, users ?? {}), currentUser)}
                    ><Fa icon={faUserPlus}/> Edit Members
                </button>
            </div>
        {/if}
    </h2>
    {#await getUser(team.leader, users) then leader}
        <div class="mb-4">
            <h4>
                Leader
            </h4>
            <div class="d-inline-flex p-2 align-items-center">
                <img class="img-thumb" src="{getPicture(leader.picture_id)}" alt="{leader.full_name}">
                <div class="ms-2">
                    <div>{leader.full_name}</div>
                    <div class="text-muted">{leader.username}</div>
                </div>
            </div>
        </div>
    {/await}
    {#if team.motd}
        <div class="mb-4">
            <h4>Message of the day</h4>
            <div class="bg-light-one p-2 rounded">
                <div class="border rounded p-2 markdown-body">
                    {@html DOMPurify.sanitize(parse(team.motd, markdownRendererOptions))}
                </div>
            </div>
        </div>
    {/if}
    <div>
        <h4>
            Members
        </h4>
        <div class="bg-light-one rounded p-2">
            {#each resolveUsers(team.members, users) as member (team.id, member.id)}
                <TeamMember {member} />
            {/each}
        </div>
    </div>
</div>


<div class="modal fade" id="modalMotdUpdate-{team.id}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="exampleModalLabel">Edit Message of the Day</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <div>
                    <textarea class="form-control" rows="20" bind:value={newMotdText}></textarea>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-danger" data-bs-dismiss="modal" onclick={handleUpdateMotd}>Update</button
                >
            </div>
        </div>
    </div>
</div>

<div class="modal fade" id="modalEditMembers-{team.id}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="exampleModalLabel">Update members</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <Select
                    items={createUserSelectList(Object.values(users), currentUser)}
                    multiple={true}
                    placeholder="Members"
                    bind:value={newMembers}
                >
                    <div slot="item" let:item let:index>
                        <User {item} />
                    </div>
                </Select>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-success" data-bs-dismiss="modal" onclick={handleUpdateMembers}>Save</button
                >
            </div>
        </div>
    </div>
</div>

<style>
    .img-thumb {
        border-radius: 50%;
        width: 64px;
    }
</style>
