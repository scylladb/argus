<script lang="ts">
    import { badgeLabel, isRowActive } from "../Common/ConfigParamFilters";
    import type { ConfigParamFilterRow } from "../Common/ConfigParamFilters";

    interface Props {
        rows: ConfigParamFilterRow[];
        offNames?: string[];
        ontoggle?: (name: string) => void;
    }

    let { rows, offNames = [], ontoggle = () => {} }: Props = $props();
</script>

<div class="d-inline-flex flex-wrap align-items-center mb-2 rounded bg-white p-2" style="row-gap: 0.5em">
    <span class="me-2 text-muted">Config parameters</span>
    {#each rows as row (row.name)}
        <button
            type="button"
            class="badge me-2 border-0 param-badge"
            class:param-badge-on={isRowActive(row, offNames)}
            class:param-badge-off={!isRowActive(row, offNames)}
            title={isRowActive(row, offNames)
                ? "Filtering by this parameter. Click to widen this widget for your session."
                : "Switched off for your session. Click to apply it again."}
            onclick={() => ontoggle(row.name)}
        >{badgeLabel(row)}</button>
    {/each}
</div>

<style>
    .param-badge {
        cursor: pointer;
    }

    .param-badge-on {
        background-color: #0d6efd;
        color: #fff;
    }

    .param-badge-off {
        background-color: #e9ecef;
        color: #6c757d;
        text-decoration: line-through;
    }
</style>
