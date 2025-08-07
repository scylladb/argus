<script lang="ts">
    import { run } from 'svelte/legacy';

    import queryString from "query-string";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { stateEncoder } from "../Common/StateManagement";
    import ReleasePlannerGridView from "../ReleasePlanner/ReleasePlannerGridView.svelte";
    import SearchBar from "../ReleasePlanner/SearchBar.svelte";
    import TestRuns from "./TestRuns.svelte";
    interface Props {
        testRuns?: any;
        workAreaAttached?: boolean;
    }

    let { testRuns = $bindable([]), workAreaAttached = false }: Props = $props();
    let additionalRuns = $state({});
    let serializedState = $state("");
    run(() => {
        serializedState = stateEncoder(testRuns);
    });

    let selectingFromGrid = $state(false);
    let release = $state(null);

    const updateUrl = function () {
        serializedState = stateEncoder(testRuns);
        let params = queryString.parse(document.location.search, {arrayFormat: "bracket"});
        params.state = serializedState;
        history.pushState({}, "", `?${queryString.stringify(params, {arrayFormat: "bracket"})}`);
    };

    /**
     *
     * @param {CustomEvent} event
     */
    const handleSearch = function(event) {
        const item = event.detail.items[0];
        switch (item.type) {
        case "test": {
            testRuns.includes(item.id) ? null: testRuns.push(item.id);
            break;
        }
        case "group": {
            fetchGroupTests(item.id);
            break;
        }
        case "release": {
            release = item;
            selectingFromGrid = true;
            break;
        }
        case "run": {
            const testId = item.testId;
            if (!testId) break;
            additionalRuns[testId] = [...(additionalRuns[testId] || []), item.id];
            testRuns.includes(item.testId) ? null: testRuns.push(item.testId);
            break;
        }
        }
        testRuns = testRuns;
        updateUrl();
    };

    const fetchGroupTests = async function (groupId) {
        try {
            const qs = queryString.stringify({ groupId });
            const res = await fetch("/api/v1/tests?" + qs);
            const json = await res.json();
            if (json.status !== "ok") {
                throw json;
            }
            json.response.forEach((test) => {
                if (!testRuns.includes(test.id)) testRuns.push(test.id);
            });
            testRuns = testRuns;
            updateUrl();
        } catch (e) {
            console.log(e);
        }
    };

    const handleGridSelect = function(e) {
        const selection = e.detail;
        selection.tests.forEach((test) => {
            testRuns.includes(test.id) ? null: testRuns.push(test.id);
        });
        selection.groups.forEach((group) => {
            fetchGroupTests(group.id);
        });
        selectingFromGrid = false;
        release = null;
        testRuns = testRuns;
        updateUrl();
    };
</script>

<div class="p-2">
    <SearchBar targetType={null} release={null} on:selected={handleSearch}/>
</div>

{#if selectingFromGrid}
    <ModalWindow widthClass="w-75" on:modalClose={() => {selectingFromGrid = false; release = null; }}>
        {#snippet title()}
                <div >Grid View</div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlannerGridView format="map" {release} on:gridViewConfirmed={handleGridSelect}/>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if Object.keys(testRuns).length > 0}
<div class="p-2 mb-1 text-end"><a href="/test_runs?state={serializedState}" class="btn btn-secondary btn-sm">Share</a></div>
<div class="accordion mb-2" id="accordionTestRuns">
    {#each testRuns as testId (testId)}
        <TestRuns
            {testId}
            additionalRuns={additionalRuns[testId] ?? []}
            parent="#accordionTestRuns"
            removableRuns={workAreaAttached}
            on:testRunRemove
            on:cloneSelect={(e) => {
                testRuns = [...testRuns, e.detail.testId];
            }}
        />
    {/each}
</div>
{:else}
<div class="row h-100">
    <div class="col p-4 align-self-center text-center ">
        <div
            class="d-inline-block border rounded p-4 text-muted"
        >
            No tests selected.
        </div>
    </div>
</div>
{/if}

<style>
</style>
