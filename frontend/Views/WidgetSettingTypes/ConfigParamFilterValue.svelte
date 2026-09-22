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
        <div class="row g-2 mb-2 align-items-center">
            <div class="col-5">
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
            <div class="col-5">
                {#if row.value === null}
                    <div class="form-control text-muted bg-light">{ANY_VALUE_LABEL}</div>
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
            <div class="col-2 d-flex gap-1">
                <button
                    class="btn btn-sm"
                    class:btn-primary={row.value === null}
                    class:btn-outline-secondary={row.value !== null}
                    disabled={!row.name}
                    title="Match any non-empty value of this parameter"
                    onclick={() => toggleAnyValue(index)}
                >Any</button>
                <button class="btn btn-sm btn-outline-danger" title="Remove this filter" onclick={() => removeRow(index)}>
                    <Fa icon={faTrash}/>
                </button>
            </div>
        </div>
        {#if duplicateAt === index}
            <div class="text-danger small mb-2">That parameter is already filtered.</div>
        {/if}
    {/each}

    <button class="btn btn-outline-primary btn-sm" onclick={addRow}>
        <Fa icon={faPlus}/> Add Parameter Filter
    </button>
</div>
