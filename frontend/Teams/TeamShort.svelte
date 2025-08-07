<script lang="ts">
    import format from "string-template";
    import { faCrown, faFolderOpen, faTrash, faUsers } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import type { Users, User as IUser } from "../Common/UserTypes";
    import { getUser } from "../Common/UserUtils";
    import { userList } from "../Stores/UserlistSubscriber";
    import { TeamManagerAPIError, TeamManagerException, TeamRoutes, type RawTeamDeleteResponse, type Team } from "./TeamUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import { applicationCurrentUser } from "../argus";
    interface Props {
        team: Team;
        selectedTeam: Team | null;
    }

    let { team, selectedTeam }: Props = $props();
    const dispatch = createEventDispatcher();
    let users: Users = $derived($userList);
    let deleting = $state(false);


    let currentUser: IUser = applicationCurrentUser;

    const handleDelete = async function () {
        deleting = true;
        try {
            const response = await fetch(format(TeamRoutes.DELETE_TEAM, { teamId: team.id }), {
                method: "DELETE"
            });
            if (!response.ok) {
                throw new TeamManagerException(`HTTP Transport Error: ${response.status}`);
            }
            const json: RawTeamDeleteResponse = await response.json();
            if (json.status === "ok") {
                dispatch("teamDeleted", team);
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (error) {
            if (error instanceof TeamManagerAPIError)
            {
                sendMessage("error", `${error.arguments[0]}`, "TeamShort::handleDelete");
            }
            console.log(error);

        } finally {
            deleting = false;
        }
    };

    const handleOpen = async function () {
        dispatch("teamOpen", team);
    };
</script>

<div class="d-flex align-items-center bg-white rounded shadow-sm m-1 p-2" role="button" class:selected={selectedTeam?.id == team.id}>
    <div>
        <div><Fa icon={team.leader == currentUser.id ? faCrown : faUsers}/> {team.name}</div>
        <div class="fs-6 text-leader">@{getUser(team.leader, users).username}</div>
    </div>
    {#if currentUser.id == team.leader}
        <div class="ms-auto">
            {#if deleting}
                <button class="btn btn-sm btn-danger"
                    ><div class="spinner-border spinner-border-sm"></div></button
                >
            {:else}
                <button class="btn btn-sm btn-danger" data-bs-toggle="modal" data-bs-target="#modalDeleteTeam-{team.id}"
                    ><Fa icon={faTrash} /></button
                >
            {/if}
        </div>
    {/if}
    <div class="{currentUser.id == team.leader ? "ms-2" : "ms-auto"}">
        <button class="btn btn-sm btn-success" onclick={handleOpen}><Fa icon={faFolderOpen} /></button>
    </div>
</div>

<div class="modal fade" id="modalDeleteTeam-{team.id}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="exampleModalLabel">Deleting a team</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">Are you sure you want to delete this team?</div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">No</button>
                <button type="button" class="btn btn-danger" data-bs-dismiss="modal" onclick={handleDelete}>Yes</button
                >
            </div>
        </div>
    </div>
</div>

<style>
    .selected {
        background-color: #0d6efd;
    }

    .text-leader {
        color: #3f3f3f;
        font-size: 0.9em;
    }
</style>
