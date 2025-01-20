<script>
    import Fa from "svelte-fa";
    import { WIDGET_TYPES, Widget } from "../Common/ViewTypes";
    import { faEdit, faList, faQuestionCircle, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher, onMount } from "svelte";
    import { titleCase } from "../Common/TextUtils";


    /**
     * @type {Widget}
     */
    export let widgetSettings = {};
    export let items = [];

    let editingSettings = false;
    const dispatch = createEventDispatcher();
    let WIDGET_DEF = WIDGET_TYPES[widgetSettings.type];
    $: WIDGET_DEF = WIDGET_TYPES[widgetSettings.type];


    const populateWidgetSettings = function() {
        Object
            .entries(WIDGET_DEF.settingDefinitions)
            .forEach(([setting, definition]) => {
                if (!widgetSettings.settings[setting]) widgetSettings.settings[setting] = definition.default;
            });
    };

    onMount(populateWidgetSettings);
    onMount(() => {
        if (!widgetSettings.filter) widgetSettings.filter = [];
    });
</script>

<div class="mb-2 rounded bg-white p-2">
    <div class="d-flex align-items-center">
        <div class="me-2"><Fa icon={faList}/> <span class="fw-bold">{widgetSettings.position}</span></div>
        <div class="flex-fill">
            <select class="form-select" bind:value={widgetSettings.type} on:change={() => populateWidgetSettings()}>
                {#each Object.entries(WIDGET_TYPES) as [type, spec] (type)}
                    <option value="{type}">{spec.friendlyName}</option>
                {/each}
            </select>
        </div>
        <div class="ms-2">
            <button class="btn btn-primary" on:click={() => (editingSettings = true)}><Fa icon={faEdit} /></button>
        </div>
        <div class="ms-2">
            <button class="btn btn-danger" on:click={() => dispatch("removeWidget", widgetSettings)}><Fa icon={faTrash} /></button>
        </div>
    </div>
</div>

{#if editingSettings}
    <div class="widget-settings-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 h-50">
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Editing <span class="fw-bold">{WIDGET_DEF.friendlyName}</span></h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            on:click={() => {
                                editingSettings = false;
                            }}
                        ></button>
                    </div>
                </div>
                <div>
                    <div>
                        <div class="mb-2">
                            Item Filter <span title="Only selected items will be shown in the widget. No selection - Show all"><Fa icon={faQuestionCircle}/></span>
                            <button class="btn btn-sm btn-outline-danger" on:click={() => (widgetSettings.filter = [])}>Clear All</button>
                        </div>
                        <select class="form-select" multiple size=10 bind:value={widgetSettings.filter}>
                            {#each items as item}
                                <option value="{item.id}"><span class="fw-bold">[{titleCase(item.type)}]</span> {item.pretty_name || item.name}</option>
                            {/each}
                        </select>
                    </div>
                    {#each Object.entries(WIDGET_DEF.settingDefinitions) as [settingName, definition] (settingName)}
                        {#if typeof definition.type !== "string"}
                            <svelte:component this={definition.type} bind:settings={widgetSettings.settings} {definition} {settingName} />
                        {:else}
                            <div>
                                {JSON.stringify(definition)}
                            </div>
                        {/if}
                    {:else}
                        <div class="text-muted text-center">No settings to configure.</div>
                    {/each}
                </div>
            </div>
        </div>
    </div>
{/if}
<style>
    .h-50 {
        width: 50%;
    }
    .widget-settings-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }
</style>
