<script lang="ts">
    import { faQuestionCircle, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import Select from "svelte-select";
    import queryString from "query-string";
    import {
        ANY_VALUE_LABEL,
        emptyRow,
        hasDuplicateName,
        normalizeRows,
    } from "../../Common/ConfigParamFilters";
    import type { ConfigParamFilterRow } from "../../Common/ConfigParamFilters";

    interface Props {
        settingName: string;
        definition: any;
        settings: any;
    }

    let { settingName, definition, settings = $bindable() }: Props = $props();

    const uid = $props.id();

    let rows: ConfigParamFilterRow[] = $state(normalizeRows(settings[settingName] ?? definition.default ?? []));
    let duplicateAt: number = $state(-1);

    settings[settingName] = rows;

    const lookup = async function (route: string, params: Record<string, string>): Promise<string[]> {
        try {
            const response = await fetch(`${route}?${queryString.stringify(params)}`);
            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            return json.response;
        } catch (error) {
            console.log(error);
            return [];
        }
    };

    const nameLookup = async function (query: string) {
        const names = await lookup("/api/v1/run_configs/param_names", { query: query ?? "" });
        return names.map((name) => ({ value: name, label: name }));
    };

    const valueLookup = function (name: string) {
        return async function (query: string) {
            const values = await lookup("/api/v1/run_configs/param_values", { name: name, query: query ?? "" });
            return values.map((value) => ({ value: value, label: value }));
        };
    };

    const replaceRow = function (index: number, row: ConfigParamFilterRow) {
        rows[index] = row;
    };

    const handleNameSelect = function (index: number, name: string) {
        if (hasDuplicateName(rows, name, index)) {
            duplicateAt = index;
            return;
        }
        duplicateAt = -1;
        replaceRow(index, { name: name, value: null });
    };

    const handleNameClear = function (index: number) {
        duplicateAt = -1;
        replaceRow(index, emptyRow());
    };

    const handleValueSelect = function (index: number, value: string | null) {
        replaceRow(index, { ...rows[index], value: value });
    };

    const toggleAnyValue = function (index: number) {
        const row = rows[index];
        replaceRow(index, { ...row, value: row.value === null ? "" : null });
    };

    const addRow = function () {
        rows.push(emptyRow());
    };

    const removeRow = function (index: number) {
        duplicateAt = -1;
        rows.splice(index, 1);
    };

    const asOption = function (value: string | null) {
        return value ? { value: value, label: value } : undefined;
    };
</script>

<div>
    <div>{definition.displayName} <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span></div>

    {#each rows as row, index}
        <div class="input-group param-row mb-2">
            <div class="param-field" title={row.name}>
                <Select
                    --item-height="auto"
                    --item-line-height="auto"
                    value={asOption(row.name)}
                    placeholder="Parameter name"
                    loadOptions={nameLookup}
                    on:select={(e) => handleNameSelect(index, e.detail.value)}
                    on:clear={() => handleNameClear(index)}
                >
                    <div slot="empty">
                        <div class="p-2 text-muted text-center">Type to search parameter names.</div>
                    </div>
                </Select>
            </div>
            <span class="input-group-text param-equals">=</span>
            <div class="param-field" title={row.value ?? ANY_VALUE_LABEL}>
                {#if row.value === null}
                    <span class="form-control d-flex align-items-center text-muted">{ANY_VALUE_LABEL}</span>
                {:else}
                    {#key row.name}
                        <Select
                            --item-height="auto"
                            --item-line-height="auto"
                            value={asOption(row.value)}
                            disabled={!row.name}
                            placeholder={row.name ? "Value" : "Pick a parameter first"}
                            loadOptions={valueLookup(row.name)}
                            on:select={(e) => handleValueSelect(index, e.detail.value)}
                            on:clear={() => handleValueSelect(index, "")}
                        >
                            <div slot="empty">
                                <div class="p-2 text-muted text-center">Type a value prefix to search.</div>
                            </div>
                        </Select>
                    {/key}
                {/if}
            </div>
            <label class="input-group-text" for="{uid}-any-{index}">
                <input
                    class="form-check-input mt-0 me-2"
                    type="checkbox"
                    id="{uid}-any-{index}"
                    disabled={!row.name}
                    checked={row.value === null}
                    onchange={() => toggleAnyValue(index)}
                >
                <span class:text-muted={!row.name}>Any</span>
            </label>
            <button class="btn btn-danger" title="Remove this filter" onclick={() => removeRow(index)}>
                <Fa icon={faTrash}/>
            </button>
        </div>
        {#if duplicateAt === index}
            <div class="text-danger small mb-2">That parameter is already filtered.</div>
        {/if}
    {/each}

    <button class="btn btn-primary btn-sm" onclick={addRow}>
        <Fa icon={faPlus}/> Add Parameter Filter
    </button>
</div>

<style>
    .param-row {
        flex-wrap: nowrap;
    }

    /* flex-basis 0 so both fields split the row evenly whatever they hold, and
       min-width 0 so a long name or URL truncates instead of widening the row. */
    .param-field {
        flex: 1 1 0;
        min-width: 0;
    }

    .param-field :global(.svelte-select),
    .param-field :global(.value-container) {
        min-width: 0;
    }

    .param-field :global(.svelte-select) {
        --border-radius: 0;
        --height: calc(1.5em + 0.75rem + 2px);
        height: 100%;
    }

    .param-field :global(.form-control) {
        height: 100%;
        border-radius: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .param-row .param-field:first-child :global(.svelte-select) {
        --border-radius: var(--bs-border-radius) 0 0 var(--bs-border-radius);
    }

    .param-equals {
        font-weight: 600;
    }
</style>
