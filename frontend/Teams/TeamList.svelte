<script lang="ts">
    import type { User } from "../Common/UserTypes";
    import { TeamRoutes, type RawTeamListResponse, type Team, TeamManagerAPIError, TeamManagerException } from "./TeamUtils";
    import format from "string-template";
    import { sendMessage } from "../Stores/AlertStore";
    import TeamShort from "./TeamShort.svelte";
    import { createEventDispatcher, onMount } from "svelte";
    import TeamCreateForm from "./TeamCreateForm.svelte";
    const dispatch = createEventDispatcher();
    interface Props {
        currentUser: User;
        selectedTeam: Team | null;
        teams: Team[];
    }

    let { currentUser, selectedTeam, teams = $bindable() }: Props = $props();

    const fetchUserTeams = async function(): Promise<Team[]> {
        try {
            const response = await fetch(format(TeamRoutes.GET_TEAMS_FOR_USER, { userId: currentUser.id }));
            if (!response.ok) {
                throw new TeamManagerException(`API Transport Error ${response.status}`);
            }
            const json: RawTeamListResponse = await response.json();
            if (json.status === "ok") {
                return json.response;
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (err) {
            if (err instanceof TeamManagerAPIError) {
                sendMessage("error", "Failed fetching teams", "TeamList::fetchUserTeams");
            }
            return [];
        }
    };

    const handleDelete = function(e: CustomEvent) {
        teams = teams.filter(t => t.id != e.detail.id);
        if (selectedTeam?.id == e.detail.id) {
            dispatch("teamClose");
        }
    };

    onMount(async () => {
        teams = await fetchUserTeams();
    });
</script>
<div class="row">
    <div class="col py-2">
        <TeamCreateForm
            on:teamCreated={async () => { teams = await fetchUserTeams();}}
        />
    </div>
</div>
{#if !teams}
    <div class="d-flex justify-content-center align-items-center p-4">
        <div class="spinner-border"></div>
        <div class="ms-2">Loading teams...</div>
    </div>
{:else}
    <h4>My Teams</h4>
    <div class="bg-light-one rounded min-vh-100 mb-2 p-2">
        {#each teams as team (team.id)}
            <TeamShort {team} {selectedTeam} on:teamDeleted={handleDelete} on:teamOpen/>
        {:else}
            <p class="text-muted text-center">No teams available.</p>
        {/each}
    </div>
{/if}
