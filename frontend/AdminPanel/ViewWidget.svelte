<script>
    import { run } from 'svelte/legacy';

    import Fa from "svelte-fa";
    import { WIDGET_TYPES, Widget } from "../Common/ViewTypes";
    import { faEdit, faList, faQuestionCircle, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher, onMount } from "svelte";
    import { titleCase } from "../Common/TextUtils";



    /**
     * @typedef {Object} Props
     * @property {Widget} [widgetSettings]
     * @property {any} [items]
     * @property {} drag
     * @property {} dragover
     * @property {} dragend
     */

    /** @type {Props} */
    let { widgetSettings = $bindable({}), items = [], dragover, drag, dragend } = $props();

    let editingSettings = $state(false);
    let isDragged = $state(false);
    const dispatch = createEventDispatcher();
    let WIDGET_DEF = $state(WIDGET_TYPES[widgetSettings.type]);
    run(() => {
        WIDGET_DEF = WIDGET_TYPES[widgetSettings.type];
    });

    const handleDragStart = function () {
        isDragged = true;
    };

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

<div
    class="mb-2 rounded bg-white p-2"
    class:is-dragged={isDragged}
    >
    <div class="d-flex align-items-center">
        <div
            class="me-2"
            role="listitem"
            draggable="true"
            style="cursor:grab"
            ondragstart={() => handleDragStart()}
            ondrag={() => drag(widgetSettings)}
            ondragover={() => dragover(widgetSettings)}
            ondragend={() => {
                isDragged = false;
                dragend(widgetSettings);
            }}
        ><Fa icon={faList}/> <span class="fw-bold">{widgetSettings.position}</span></div>
        <div class="flex-fill">
            <select class="form-select" bind:value={widgetSettings.type} onchange={() => populateWidgetSettings()}>
                {#each Object.entries(WIDGET_TYPES) as [type, spec] (type)}
                    <option value="{type}">{spec.friendlyName}</option>
                {/each}
            </select>
        </div>
        <div class="ms-2">
            <button class="btn btn-primary" onclick={() => (editingSettings = true)}><Fa icon={faEdit} /></button>
        </div>
        <div class="ms-2">
            <button class="btn btn-danger" onclick={() => dispatch("removeWidget", widgetSettings)}><Fa icon={faTrash} /></button>
        </div>
    </div>
</div>

{#if editingSettings}
    <div class="widget-settings-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 w-50">
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Editing <span class="fw-bold">{WIDGET_DEF.friendlyName}</span></h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            onclick={() => {
                                editingSettings = false;
                            }}
                        ></button>
                    </div>
                </div>
                <div>
                    <div>
                        <div class="mb-2">
                            Item Filter <span title="Only selected items will be shown in the widget. No selection - Show all"><Fa icon={faQuestionCircle}/></span>
                            <button class="btn btn-sm btn-outline-danger" onclick={() => (widgetSettings.filter = [])}>Clear All</button>
                        </div>
                        <select class="form-select" multiple size=10 bind:value={widgetSettings.filter}>
                            {#each items as item}
                                <option value="{item.id}">[{titleCase(item.type)}] {item.pretty_name || item.name}</option>
                            {/each}
                        </select>
                    </div>
                    {#each Object.entries(WIDGET_DEF.settingDefinitions) as [settingName, definition] (settingName)}
                        {#if typeof definition.type !== "string"}
                            <definition.type bind:settings={widgetSettings.settings} {definition} {settingName} />
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
    .w-50 {
        width: 50%;
    }

    .is-dragged {
        opacity: 10%;
        border: dotted 5px black;
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
