<script lang="ts">
    import { createBubbler, stopPropagation } from 'svelte/legacy';

    const bubble = createBubbler();
    import {createEventDispatcher} from "svelte";
    import queryString from "query-string";
    import {sendMessage} from "../Stores/AlertStore";
    import ResultsGraph from "./ResultsGraph.svelte";
    import Filters from "./Components/Filters.svelte";
    import {faMinus, faPlus} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import GraphFilters from "./Components/GraphFilters.svelte";

    interface Props {
        test_id?: string;
    }

    let { test_id = "" }: Props = $props();
    let graphs: any[] = $state([]);
    let allGraphs: any[] = [];
    let filteredGraphs: any[] = $state([]);
    let releasesFilters: Record<string, boolean> = $state({});
    let ticks: Record<string, any> = $state({});
    let width = 500;
    let height = 350;
    let startDate = "";
    let endDate = "";
    let dateRange = $state(6);
    let showCustomInputs = false;
    let graphViews: {
        test_id: string;
        id: string;
        name: string;
        description: string;
        graphs: Record<string, any>;
    }[] = $state([]);
    let showModal = $state(false);
    let activeTab = $state(0);
    let form = $state({name: "", description: ""});
    let showAddGraphModal = $state(false);
    let showRemoveGraphModal = $state(false);
    let selectedGraph: any = $state();
    let selectedView = $state("");

    let allTabs = $derived(["All Graphs", ...graphViews.map((v) => v.name), "+ View"]);
    const dispatch = createEventDispatcher();

    const dispatchRunClick = (e) => {
        dispatch("runClick", {runId: e.detail.runId});
    };

    const generateRandomHash = () => {
        return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    };

    const handleDateChange = (event) => {
        startDate = event.detail.startDate;
        endDate = event.detail.endDate;
        fetchTestResults(test_id);
    };


    async function fetchTestResults(testId: string) {
        try {
            const params = queryString.stringify({testId: testId, startDate, endDate});
            const res = await fetch(`/api/v1/test-results?${params}`);
            if (res.status !== 200) throw new Error(`HTTP Error ${res.status}`);

            const data = await res.json();
            if (data.status !== "ok") throw new Error(`API Error: ${data.message}`);

            allGraphs = data.response.graphs.map((g: any) => ({
                ...g,
                id: generateRandomHash(),
            }));
            ticks = data.response.ticks;
            graphs = allGraphs;
            graphViews = data.response.graph_views;
            releasesFilters = Object.fromEntries(
                data.response.releases_filters.map((r: string) => [r, true])
            );
        } catch (e) {
            sendMessage("error", "A backend error occurred", "ResultsGraphs::fetchTestResults");
            console.error(e);
        }
    }

    function handleTabClick(i: number) {
        if (allTabs[i] === "+ View") showModal = true;
        else activeTab = i;
        if (activeTab > 0) graphs = Object.keys(graphViews[activeTab - 1].graphs).map((g) => getGraphsByName(g)[0]);
        else graphs = allGraphs;
    }

    function closeModal() {
        showModal = false;
    }

    function getGraphsByName(graphName: string) {
        return allGraphs.filter((g) => g.options?.plugins?.title?.text === graphName);
    }

    function openAddGraphModal(g: any) {
        selectedGraph = g;
        showAddGraphModal = true;
    }

    function openRemoveGraphModal(g: any) {
        selectedGraph = g;
        showRemoveGraphModal = true;
    }

    function closeAddGraphModal() {
        showAddGraphModal = false;
    }

    function closeRemoveGraphModal() {
        showRemoveGraphModal = false;
    }

    async function saveNewView() {
        const payload = {
            testId: test_id,
            name: form.name,
            description: form.description,
        };
        try {
            const res = await fetch("/api/v1/create-graph-view", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`Error: ${res.status}`);
            const data = await res.json();
            if (data.status !== "ok") throw new Error(data.message);

            graphViews = [...graphViews, data.response];
            form = {name: "", description: ""};
            closeModal();
        } catch (e) {
            sendMessage("error", "Failed to create graph view", "saveNewView");
        }
    }

    async function updateArgusGraphView(view: {
        id: string;
        name: string;
        description: string;
        graphs: Record<string, any>;
    }) {
        const payload = {
            testId: test_id,
            id: view.id,
            name: view.name,
            description: view.description,
            graphs: view.graphs,
        };

        try {
            const res = await fetch("/api/v1/update-graph-view", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`Error: ${res.status}`);
            const data = await res.json();
            if (data.status !== "ok") throw new Error(data.message);

            const idx = graphViews.findIndex((v) => v.id === view.id);
            if (idx !== -1) graphViews[idx] = data.response;
        } catch (e) {
            sendMessage("error", "Failed to update graph view", "updateArgusGraphView");
        }
    }

    function addGraphToView() {
        if (!selectedView) return;
        const idx = graphViews.findIndex((v) => v.name === selectedView);
        if (idx === -1) return;

        graphViews[idx].graphs = {
            ...graphViews[idx].graphs,
            [selectedGraph.options.plugins.title.text]: "{}",
        };

        updateArgusGraphView(graphViews[idx]);
        closeAddGraphModal();
    }

    function removeGraph() {
        if (!selectedGraph) return;

        const activeViewId = graphViews[activeTab - 1]?.id;
        const idx = graphViews.findIndex((v) => v.id === activeViewId);
        if (idx === -1) return;

        const graphName = selectedGraph?.options?.plugins?.title?.text;
        delete graphViews[idx].graphs[graphName];
        graphs = Object.keys(graphViews[activeTab - 1].graphs).map((g) => getGraphsByName(g)[0]);

        updateArgusGraphView(graphViews[idx]);
        closeRemoveGraphModal();
    }
    const handleReleaseChange = () => {
        filteredGraphs = [...filteredGraphs];
    };

</script>

<GraphFilters
        bind:dateRange
        bind:releasesFilters
        on:dateChange={handleDateChange}
        on:releaseChange={handleReleaseChange}
/>

<ul class="nav nav-tabs mb-3">
    {#each allTabs as t, i}
        <li class="nav-item">
            <a class="nav-link {activeTab === i ? 'active' : ''}" onclick={() => handleTabClick(i)}>{t}</a>
        </li>
    {/each}
</ul>
<h5 class="text-center">{graphViews[activeTab - 1]?.description || "All graphs"}</h5>
{#key graphs}
    <Filters {graphs} bind:filteredGraphs/>
{/key}
<div class="charts-container">
    {#key filteredGraphs}
    {#each filteredGraphs as graph (graph.id)}
        <div class="chart-container"
             class:big-size={filteredGraphs.length < 2}>
            {#if activeTab === 0}
                    <button class="add-btn" onclick={() => openAddGraphModal(graph)} title="add to graph view">
                        <Fa icon={faPlus}/>
                    </button>
                {:else}
                    <button class="add-btn" onclick={() => openRemoveGraphModal(graph)} title="Remove from graph view">
                        <Fa icon={faMinus}/>
                    </button>
                {/if}
            <ResultsGraph
                    {graph}
                    {ticks}
                    height={filteredGraphs.length === 1 ? 600 : height}
                    width={filteredGraphs.length === 1 ? 1000 : width}
                    test_id={test_id}
                    index={graph.id}
                    releasesFilters={releasesFilters}
                    on:runClick={dispatchRunClick}
            />
        </div>
    {/each}
        {/key}
</div>

{#if showModal}
    <div class="modal show d-block" tabindex="-1" role="dialog" onclick={closeModal}>
        <div class="modal-dialog" role="document" onclick={stopPropagation(bubble('click'))}>
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">New View</h5>
                    <button type="button" class="close" onclick={closeModal}>&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Name</label>
                        <input class="form-control" type="text" bind:value={form.name}/>
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <textarea class="form-control" bind:value={form.description}></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-primary" onclick={saveNewView}>Save</button>
                    <button type="button" class="btn btn-secondary" onclick={closeModal}>Cancel</button>
                </div>
            </div>
        </div>
    </div>
{/if}

{#if showAddGraphModal}
    <div class="modal show d-block" tabindex="-1" role="dialog" onclick={closeAddGraphModal}>
        <div class="modal-dialog" role="document" onclick={stopPropagation(bubble('click'))}>
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Add Graph to View</h5>
                    <button type="button" class="close" onclick={closeAddGraphModal}>&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Select Graph View</label>
                        <select class="form-control" bind:value={selectedView}>
                            <option value="" disabled>Select a view</option>
                            {#each graphViews as v}
                                <option value={v.name}>{v.name}</option>
                            {/each}
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick={addGraphToView}>Add</button>
                    <button class="btn btn-secondary" onclick={closeAddGraphModal}>Cancel</button>
                </div>
            </div>
        </div>
    </div>
{/if}

{#if showRemoveGraphModal}
    <div class="modal show d-block" tabindex="-1" role="dialog" onclick={closeRemoveGraphModal}>
        <div class="modal-dialog" role="document" onclick={stopPropagation(bubble('click'))}>
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Remove Graph?</h5>
                    <button type="button" class="close" onclick={closeRemoveGraphModal}>&times;</button>
                </div>
                <div class="modal-body">
                    <p>Remove <strong>{selectedGraph?.options?.plugins?.title?.text}</strong> from this view?</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-danger" onclick={removeGraph}>Remove</button>
                    <button class="btn btn-secondary" onclick={closeRemoveGraphModal}>Cancel</button>
                </div>
            </div>
        </div>
    </div>
{/if}

<style>
    .charts-container {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        align-items: center;
    }

    .chart-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 10px;
        position: relative;
    }

    .big-size {
        width: 90%;
    }

    .add-btn {
        position: absolute;
        top: 10px;
        left: 10px;
        background: none;
        border: none;
        cursor: pointer;
        color: #888;
        font-size: 1.2em;
        z-index: 999;
    }

    .add-btn:hover {
        color: #333;
    }
</style>
