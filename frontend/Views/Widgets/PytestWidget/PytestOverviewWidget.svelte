<script lang="ts">
    import PytestCollapseHelper from "./PytestCollapseHelper.svelte";
    import PytestFlatHelper from "./PytestFlatHelper.svelte";
    import ViewPytestOverview from "./ViewPytestOverview.svelte";

    interface Props {
        dashboardObject: Record<string, unknown>;
        /**
     * @type {string}
     */
        dashboardObjectType: string;
        settings: {
        collapsed: boolean,
        enabledStatuses: string[]
    };
    }

    let { dashboardObject, dashboardObjectType, settings }: Props = $props();

    let opened = $state(false);

    const SvelteComponent = $derived(settings.collapsed ? PytestCollapseHelper : PytestFlatHelper);
</script>

<SvelteComponent on:open={() => (opened = true)}>
{#if opened}
    <ViewPytestOverview {dashboardObject} {dashboardObjectType} {settings}/>
{/if}
</SvelteComponent>
