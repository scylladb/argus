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
{:else if reported && cost}
    <div class="p-2">
        <div class="row g-2 mb-3">
            <div class="col-12 col-md-6">
                <div class="border rounded p-3 h-100">
                    <div class="text-muted small text-uppercase">Estimated</div>
                    <div class="fs-4">{formatAmount(cost.estimated_cost)}</div>
                </div>
            </div>
            <div class="col-12 col-md-6">
                <div class="border rounded p-3 h-100">
                    <div class="text-muted small text-uppercase">Actual</div>
                    <div class="fs-4">{formatAmount(cost.actual_cost)}</div>
                </div>
            </div>
        </div>

        {#if cost.items.length > 0}
            <div class="table-responsive">
                <table class="table table-sm align-middle">
                    <thead>
                        <tr>
                            <th scope="col">Item</th>
                            <th scope="col">Pricing tier</th>
                            <th scope="col" class="text-end">Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each categories as group (group.category)}
                            <tr class="table-light">
                                <th scope="rowgroup" colspan="2">{group.category}</th>
                                <th scope="rowgroup" class="text-end">{formatAmount(group.subtotal)}</th>
                            </tr>
                            {#each group.items as item (item.name)}
                                <tr>
                                    <td>
                                        {item.name}
                                        {#if item.leaked}
                                            <span class="badge bg-secondary ms-1">Leaked</span>
                                        {/if}
                                    </td>
                                    <td class="text-muted">{item.pricing_tier ?? "—"}</td>
                                    <td class="text-end">{formatAmount(item.cost)}</td>
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
