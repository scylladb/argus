<script lang="ts">
    import PytestCollapseHelper from "./PytestCollapseHelper.svelte";
    import PytestFlatHelper from "./PytestFlatHelper.svelte";
    import ViewPytestOverview from "./ViewPytestOverview.svelte";
    export let dashboardObject: Record<string, unknown>;
    /**
     * @type {string}
     */
    export let dashboardObjectType: string;
    export let settings: {
        collapsed: boolean,
        enabledStatuses: string[]
    };

    let opened = false;
</script>

<svelte:component this={settings.collapsed ? PytestCollapseHelper : PytestFlatHelper} on:open={() => (opened = true)}>
{#if opened}
    <ViewPytestOverview {dashboardObject} {dashboardObjectType} {settings}/>
{/if}
</svelte:component>
