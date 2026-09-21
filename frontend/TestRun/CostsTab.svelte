<script lang="ts">
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faCoins } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../Common/ApiUtils";
    import { sendMessage } from "../Stores/AlertStore";

    interface CostItem {
        name: string;
        category: string;
        cost: number;
        pricing_tier: string | null;
        leaked: boolean;
    }

    interface RunCost {
        estimated_cost: number | null;
        actual_cost: number | null;
        items: CostItem[];
        by_category: Record<string, number>;
    }

    let { runId }: { runId: string } = $props();

    let cost: RunCost | undefined = $state();
    let fetching = $state(true);
    let failed = $state(false);

    const CATEGORY_LABELS: Record<string, string> = {
        db_node: "Database nodes",
        oracle_node: "Oracle nodes",
        loader: "Loaders",
        monitor: "Monitors",
        sct_runner: "SCT runner",
        storage: "Storage",
        network: "Network",
    };

    const categoryLabel = function (category: string): string {
        const known = CATEGORY_LABELS[category];
        if (known) return known;
        const spaced = category.replaceAll("_", " ").trim();
        return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : category;
    };

    const formatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

    const formatAmount = function (amount: number | null | undefined): string {
        if (amount === null || amount === undefined) return "Not reported";
        return formatter.format(amount);
    };

    let categories = $derived.by(() => {
        if (!cost) return [];
        const grouped = new Map<string, CostItem[]>();
        for (const item of cost.items) {
            const bucket = grouped.get(item.category) ?? [];
            bucket.push(item);
            grouped.set(item.category, bucket);
        }
        return [...grouped.entries()].map(([category, items]) => ({
            category,
            items,
            subtotal: cost?.by_category?.[category] ?? null,
        }));
    });

    let reported = $derived(
        !!cost && (cost.estimated_cost !== null || cost.actual_cost !== null || cost.items.length > 0)
    );

    const fetchCost = async function () {
        try {
            cost = await fetchJson(`/api/v1/cost/run/${runId}`);
        } catch (e) {
            failed = true;
            if (e instanceof Error) {
                sendMessage("error", e.message, "CostsTab::fetchCost");
            } else {
                sendMessage("error", "Backend error during cost fetch.", "CostsTab::fetchCost");
                console.trace();
            }
        } finally {
            fetching = false;
        }
    };

    onMount(async () => {
        await fetchCost();
    });
</script>

{#if fetching}
    <div class="text-center text-muted p-4">
        <span class="spinner-border spinner-border-sm"></span> Fetching costs...
    </div>
{:else if failed}
    <div class="text-center text-danger p-4">
        Could not load the cost of this run. Reload the page to try again.
    </div>
{:else if reported && cost}
    <div class="p-2">
        <div class="row g-2 mb-3">
            <div class="col-12 col-md-6">
                <div class="cost-summary rounded p-3 h-100">
                    <div class="text-muted small text-uppercase">Estimated</div>
                    <div class="fs-4">{formatAmount(cost.estimated_cost)}</div>
                </div>
            </div>
            <div class="col-12 col-md-6">
                <div class="cost-summary rounded p-3 h-100">
                    <div class="text-muted small text-uppercase">Actual</div>
                    <div class="fs-4">{formatAmount(cost.actual_cost)}</div>
                </div>
            </div>
        </div>

        {#if cost.items.length > 0}
            <div class="table-responsive">
                <table class="table table-bordered border">
                    <thead>
                        <tr>
                            <th scope="col" class="align-middle">Item</th>
                            <th scope="col" class="text-center align-middle">Pricing tier</th>
                            <th scope="col" class="text-end align-middle">Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each categories as group (group.category)}
                            <tr class="cost-category">
                                <th scope="rowgroup" colspan="2" class="align-middle">
                                    {categoryLabel(group.category)}
                                </th>
                                <th scope="rowgroup" class="text-end align-middle">
                                    {formatAmount(group.subtotal)}
                                </th>
                            </tr>
                            {#each group.items as item (item.name)}
                                <tr>
                                    <td class="align-middle">
                                        {item.name}
                                        {#if item.leaked}
                                            <span class="badge bg-secondary ms-1">Leaked</span>
                                        {/if}
                                    </td>
                                    <td class="text-center align-middle">{item.pricing_tier ?? "—"}</td>
                                    <td class="text-end align-middle">{formatAmount(item.cost)}</td>
                                </tr>
                            {/each}
                        {/each}
                    </tbody>
                </table>
            </div>
        {:else}
            <div class="text-center text-muted p-2">
                <Fa icon={faCoins} /> No cost items were reported for this run.
            </div>
        {/if}
    </div>
{:else}
    <div class="text-center text-muted p-4">No cost reported for this run.</div>
{/if}

<style>
    .cost-summary {
        background-color: #ededed;
        color: #212529;
    }

    .cost-category > th {
        --bs-table-bg: #e9ecef;
        --bs-table-color: #212529;
    }

    :global([data-bs-theme="dark"]) .cost-summary {
        background-color: #2b3035;
        color: #dee2e6;
    }

    :global([data-bs-theme="dark"]) .cost-category > th {
        --bs-table-bg: #343a40;
        --bs-table-color: #dee2e6;
    }
</style>
