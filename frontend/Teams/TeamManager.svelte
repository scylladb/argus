<script lang="ts">
    import { run } from 'svelte/legacy';

    import format from "string-template";
    import { onMount } from "svelte";
    import { applicationCurrentUser } from "../argus";
    import type { User as IUser, Users } from "../Common/UserTypes";
    import { userList } from "../Stores/UserlistSubscriber";
    import TeamDetail from "./TeamDetail.svelte";
    import TeamList from "./TeamList.svelte";
    import { TeamRoutes, type RawTeamGetResponse, type Team } from "./TeamUtils";

    let users: Users = $state({});
    run(() => {
        users = $userList;
    });

    let currentUser: IUser = applicationCurrentUser;
    let selectedTeam: Team | null = $state();
    let teams: Team[] = $state([]);


    const getSelectedTeam = async function(params: string) {
        let qs = new URLSearchParams(params);
        let savedTeam = qs.get("selected");
        if (savedTeam) {
            let response = await fetch(format(TeamRoutes.GET_TEAM, { teamId: savedTeam }));
            let json: RawTeamGetResponse = await response.json();
            if (json.status === "ok") {
                selectedTeam = json.response;
            } else {
                history.pushState({}, "", "?");
            }
        }
    };

    const handleTeamUpdated = function (event: CustomEvent) {
        let updatedTeam: Team = event.detail;
        let teamIdx = teams.findIndex(t => t.id == updatedTeam.id);
        teams[teamIdx] = updatedTeam;
    };

    onMount(() => {
        getSelectedTeam(document.location.search);
    });
</script>


<div class="row min-vh-100">
    {#if Object.keys(users).length > 0}
        <div class="col-2 border-end">
            <TeamList
                bind:teams={teams}
                {currentUser}
                {selectedTeam}
                on:teamOpen={(e) => {
                    selectedTeam = e.detail;
                    if (selectedTeam) {
                        history.pushState({}, "", `?selected=${selectedTeam.id}`);
                    }
                }}
                on:teamClose={() => {
                    selectedTeam = null;
                    history.pushState({}, "", "?");
                }}
            />
        </div>
        <div class="col-10 ">
            {#if selectedTeam}
                <TeamDetail team={selectedTeam} on:teamUpdated={handleTeamUpdated}/>
            {:else}
                <div class="text-center mt-4">
                    <div class="d-inline-block text-muted text-center p-4 border rounded">No team selected.</div>
                </div>
            {/if}
        </div>
    {:else}
        <div class="col">
            <p class="text-muted fs-3 text-center m-4 p-2">Loading Users...</p>
        </div>
    {/if}
</div>
