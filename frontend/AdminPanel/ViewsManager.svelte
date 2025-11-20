<script>
    import { onMount } from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import Fa from "svelte-fa";
    import { faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";
    import ViewWidget from "./ViewWidget.svelte";
    import { ADD_ALL_ID, Widget, WIDGET_TYPES } from "../Common/ViewTypes";
    import queryString from "query-string";
    import * as urlSlug from "url-slug";
    import Select from "svelte-select";
    import ViewSelectItem from "./ViewSelectItem.svelte";
    import { titleCase } from "../Common/TextUtils";
    import ViewListItem from "./ViewListItem.svelte";
    import ModalWindow from "../Common/ModalWindow.svelte";

    let allViews = $state([]);

    const VIEW_CREATE_TEMPLATE = {
        name: "",
        description: "",
        displayName: "",
        settings: "{}",
        items: [],
    };

    /**
     * @type {Widget[]}
     */
    let newWidgets = $state([]);
    let lastHits = [];
    let newView = $state(Object.assign({}, VIEW_CREATE_TEMPLATE));
    let selectedItems = $state([]);
    let lockForm = $state(false);
    let draggedWidget = $state(null);
    let editingExistingView = $state(false);
    let testSearcherValue = $state();
    let errorPopup = $state(false);
    let errorTitle = $state("");
    let errorMessage = $state("");
    let errorCallback = $state();


    const fetchAllViews = async function() {
        try {
            const response = await fetch("/api/v1/views/all");

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            allViews = json.response;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching views.\nMessage: ${error.response.arguments[0]}`,
                    "ViewManager::fetchAll"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view fetch",
                    "ViewManager::fetchAll"
                );
                console.log(error);
            }
        }
    };

    /**
     *
     * @param {{type: string}[]} viewWidgets
     */
    const checkIfViewSupported = function(viewWidgets) {
        for (const widget of viewWidgets) {
            if (!WIDGET_TYPES[widget.type]) {
                return false;
            }
        }
        return true;
    };

    const handleViewUpdateRequest = function(e, force = false) {
        resetForm();
        let viewForUpdate = e.detail;
        let widgets = JSON.parse(viewForUpdate.widget_settings);
        if (!checkIfViewSupported(widgets) && !force) {
            errorTitle = "Unsupported widget found";
            errorMessage = "This view contains unsupported widgets. Editing said view will result in the loss of those widgets.";
            errorPopup = true;
            errorCallback = handleViewUpdateRequest.bind(undefined, e, true);
            return;
        } else if (force) {
            widgets = widgets.filter(w => WIDGET_TYPES[w.type]);
            widgets.forEach((w, idx) => w.position = idx + 1);
        }
        newWidgets = widgets;
        newView = {
            id: viewForUpdate.id,
            name: viewForUpdate.name,
            plan_id: viewForUpdate.plan_id,
            description: viewForUpdate.description,
            displayName: viewForUpdate.display_name,
            settings: viewForUpdate.widget_settings,
            items: viewForUpdate.items,
        };
        editingExistingView = true;
    };

    const viewActionDispatch = async function (e) {
        return editingExistingView ? updateView(e) : createView(e);
    };

    const updateView = async function (e) {
        try {
            lockForm = true;
            const params = {
                viewId: newView.id,
                updateData: {
                    name: newView.name,
                    description: newView.description,
                    display_name: newView.displayName,
                    plan_id: newView.plan_id || null,
                    items: newView.items.map(item => `${item.type}:${item.id}`),
                    widget_settings: JSON.stringify(newWidgets),
                }
            };
            const response = await fetch("/api/v1/views/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(params),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            resetForm();
            await fetchAllViews();

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when updating a view.\nMessage: ${error.response.arguments[0]}`,
                    "ViewManager::update"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view update",
                    "ViewManager::update"
                );
                console.log(error);
            }
        } finally {
            lockForm = false;
        }
    };


    const createView = async function (e) {
        try {
            lockForm = true;
            const params = {
                name: newView.name,
                description: newView.description,
                displayName: newView.displayName,
                items: newView.items.map(item => `${item.type}:${item.id}`),
                settings: JSON.stringify(newWidgets),
            };
            validateViewParams(params);
            const response = await fetch("/api/v1/views/create", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(params),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            resetForm();
            await fetchAllViews();

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when creating a view.\nMessage: ${error.response.arguments[0]}`,
                    "ViewManager::create"
                );
            } else if (error?.cause == "validation") {
                console.log("Validation failed...");
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view creation",
                    "ViewManager::create"
                );
                console.log(error);
            }
        } finally {
            lockForm = false;
        }
    };

    const deleteView = async function (viewId) {
        try {
            lockForm = true;
            const params = {
                viewId: viewId
            };
            const response = await fetch("/api/v1/views/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(params),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            resetForm();
            await fetchAllViews();

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when deleting a view.\nMessage: ${error.response.arguments[0]}`,
                    "ViewManager::delete"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view deletion",
                    "ViewManager::delete"
                );
                console.log(error);
            }
        } finally {
            lockForm = false;
        }
    };

    /**
     * @param {string} query
     */
    const testLookup = async function (query) {
        try {
            const params = {
                query: query
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/views/search?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            lastHits = json.response.hits;
            return json.response.hits.slice(0, 100);

        } catch (error) {
            console.log(error);
        }
    };

    const handleAllItemSelect = function() {
        newView.items = [
            ...newView.items,
            ...lastHits
                .filter(i => i.id != ADD_ALL_ID
                ).map(item => {
                    return {
                        name: item.pretty_name || item.name,
                        release: item.release?.name,
                        group: item.group?.pretty_name || item.group?.name,
                        type: item.type,
                        id: item.id,
                    };
                })];
        testSearcherValue = undefined;
    };

    const handleItemSelect = function(e) {
        const item = e.detail;
        if (item.id == ADD_ALL_ID) return handleAllItemSelect();
        newView.items = [...newView.items, {
            name: item.pretty_name || item.name,
            release: item.release?.name,
            group: item.group?.pretty_name || item.group?.name,
            type: item.type,
            id: item.id,
        }];
        testSearcherValue = undefined;
    };

    const removeSelectedItem = function(id, key) {
        newView.items = newView.items.filter(v => v.id != id);
        selectedItems = selectedItems.filter(v => v != key);
    };

    const createNewWidget = function () {
        let widget = new Widget(newWidgets.length + 1);
        newWidgets = [...newWidgets, widget];
    };

    const reflowWidgetPositions = function () {
        newWidgets.forEach((v, idx) => {
            v.position = idx + 1;
        });
    };

    const validateViewParams = function (params) {
        const REQUIRED_PARAMS = ["name", "tests", "settings"];
        Object.entries(params).forEach((([name, value]) => {
            if (REQUIRED_PARAMS.includes(name)) {
                if (!value) {
                    const message = `${titleCase(name)} cannot be empty!`;
                    onValidationError(message);
                    throw new Error(message, { cause: "validation" });
                }
            }
        }));
    };

    const onValidationError = function(message) {
        sendMessage("error", message, "ViewManager::validateNewView");
    };

    const handleWidgetDrag = function (widgetSettings) {
        draggedWidget = widgetSettings;
    };

    const handleWidgetDragOver = function (widgetSettings) {
        let draggedIndex = newWidgets.findIndex((w) => w.position == draggedWidget.position);
        let draggedOverIndex = newWidgets.findIndex((w) => w.position == widgetSettings.position);
        if (draggedIndex == draggedOverIndex) return;
        let oldWidget = newWidgets[draggedIndex];
        newWidgets[draggedIndex] = newWidgets[draggedOverIndex];
        newWidgets[draggedOverIndex] = oldWidget;

    };

    const handleWidgetDragEnd = function (widgetSettings) {
        draggedWidget = null;
        reflowWidgetPositions();
    };

    const resetForm = function () {
        newWidgets = [];
        selectedItems = [];
        editingExistingView = false;
        newView = Object.assign({}, VIEW_CREATE_TEMPLATE);
    };

    /**
     * @param {CustomEvent} e
     */
    const removeWidget = function(e) {
        /**
         * @type {Widget}
         */
        let widget = e.detail;
        newWidgets = newWidgets.filter(v => v.position != widget.position);
        reflowWidgetPositions();
    };


    onMount(() => {
        fetchAllViews();
    });
</script>

{#if errorPopup}
    <ModalWindow on:modalClose={() => {
        errorTitle = "";
        errorMessage = "";
        errorPopup = false;
    }}>
        {#snippet title()}
                <div >
                {errorTitle}
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <p>{errorMessage}</p>
                <div>
                    <button class="btn btn-danger" onclick={() => {
                    errorTitle = "";
                    errorMessage = "";
                    errorPopup = false;
                    errorCallback();
                    errorCallback = undefined;
                }}>Edit Anyway</button>
                    <button class="btn btn-secondary" onclick={() => {
                    errorTitle = "";
                    errorMessage = "";
                    errorPopup = false;
                    errorCallback = undefined;
                }}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

<div class="bg-white rounded p-2 shadow-sm my-2">
    <div>
        <h4>View Manager</h4>
    </div>
    <div class="position-relative">
        <div class:d-none={!lockForm} class="position-absolute w-100 h-100" style="background-color: rgba(0,0,0,0.6); z-index: 9999"></div>
        <div class="rounded m-2 shadow-sm bg-white">
            Create new
            <div class="d-flex flex-column flex-fill p-2">
                <input class="form-control mb-2" type="text" placeholder="Name (internal)" disabled bind:value={newView.name}>
                <input class="form-control mb-2" type="text" placeholder="Display name" onchange={() => newView.name = urlSlug.convert(newView.displayName)} bind:value={newView.displayName}>
                <textarea class="form-control mb-2" type="text" placeholder="Description (optional)" bind:value={newView.description}></textarea>
                <input class="form-control mb-2" type="text" placeholder="Plan ID (internal)" bind:value={newView.plan_id}>
                <div class="mb-2">
                    <Select
                        --item-height="auto"
                        --item-line-height="auto"
                        id="viewSelectComponent"
                        inputAttributes={{ class: "form-control" }}
                        bind:value={testSearcherValue}
                        placeholder="Search for tests..."
                        label="name"
                        itemId="id"
                        loadOptions={testLookup}
                        on:select={handleItemSelect}
                    >
                        <div slot="empty">
                            <div class="p-2 text-muted text-center">
                                Type to search. Can be: Test name, Release name, Group name.
                            </div>
                        </div>
                        <div slot="item" let:item let:index>
                            <ViewSelectItem {item} />
                        </div>
                    </Select>
                </div>
                <select class="form-select mb-2" size=10 multiple bind:value={selectedItems}>
                    {#each newView.items as item}
                        <option value="{item.type}:{item.id}" ondblclick={() => removeSelectedItem(item.id, `${item.type}:${item.id}`)}>
                            [{titleCase(item.type).at(0)}] {item.pretty_name || item.display_name || item.name}
                            {#if item.release}
                                    - {item.release}
                            {/if}
                            {#if item.group}
                                    - {item.group}
                            {/if}
                        </option>
                    {:else}
                        <option value="!!">No tests selected.</option>
                    {/each}
                </select>
                <button class="btn mb-2" class:btn-danger={newView.items.length} class:btn-secondary={!newView.items.length} disabled={newView.items.length == 0} onclick={() => (newView.items = [])}><Fa icon={faTrash}/> Remove all</button>
                <div class="p-2">
                    <div>Widget builder</div>
                    <div class="rounded bg-light-one p-2" style="min-height: 256px; max-height: 512px; overflow-y: scroll">
                        <div class="text-end mb-3">
                            <button
                                class="btn btn-success"
                                onclick={() => createNewWidget()}
                            >
                                <Fa icon={faPlus} />
                            </button>
                        </div>
                        {#each newWidgets as widget, idx (widget.position)}
                            <ViewWidget
                                bind:widgetSettings={newWidgets[idx]}
                                items={newView.items}
                                on:removeWidget={removeWidget}
                                drag={(widgetSettings) => handleWidgetDrag(widgetSettings)}
                                dragover={(widgetSettings) => handleWidgetDragOver(widgetSettings)}
                                dragend={(widgetSettings) => handleWidgetDragEnd(widgetSettings)}
                            />
                        {/each}
                    </div>
                </div>
                <button class="btn mb-2" class:btn-success={!editingExistingView} class:btn-warning={editingExistingView} onclick={viewActionDispatch}>{editingExistingView ? "Update" : "Create"} view</button>
                <button class="btn btn-secondary" onclick={resetForm}>Reset</button>
            </div>
        </div>
    </div>
    <div class="rounded p-2 m-2 shadow-sm">
        All Views
        <div>
            {#each allViews as view (view.id)}
                <ViewListItem {view} on:viewUpdateRequested={handleViewUpdateRequest} on:delete={(e) => deleteView(e.detail)}/>
            {:else}
                <div>No views created.</div>
            {/each}
        </div>
    </div>
</div>
