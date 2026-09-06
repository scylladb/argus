/**
 * Cost helpers for SCT cloud resources (ARGUS-205).
 *
 * All cost math happens in SCT — Argus stores what it is told and only sums it for
 * display. The one derived value here is the *live* cost of a still-running resource:
 * `elapsed hours × price_per_hour`, using the rate SCT reported at creation. Argus does
 * no pricing lookup of its own.
 *
 * A missing price is `null`/`undefined`, never `0`: SCT maps an unknown rate to `null`
 * so an unpriced resource is never rendered as free. We treat a non-positive number the
 * same way, so an old or buggy client sending `0` cannot produce a false zero either.
 */

export interface CostInstanceInfo {
    creation_time?: number | null;
    termination_time?: number | null;
    price_per_hour?: number | null;
    cost?: number | null;
    is_spot?: boolean | null;
}

export interface CostResource {
    state?: string;
    instance_info?: CostInstanceInfo | null;
}

export interface RunCostSummary {
    /** Sum of every known cost, in USD. */
    total: number;
    /** True when at least one resource has no cost we can account for. */
    partial: boolean;
    /** Number of resources contributing to `total`. */
    known: number;
    /** Number of resources with an unknown cost. */
    unknown: number;
}

const RUNNING_STATE = "running";

/** A usable money value: a finite, strictly positive number. */
const isKnownAmount = function (value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value) && value > 0;
};

/**
 * Cost of a single resource in USD, or `null` when it cannot be determined.
 *
 * A terminated resource is worth exactly what SCT reported at termination — Argus never
 * back-fills it from the rate, since the elapsed time it has is when it was *told* about
 * the instance, not when the instance actually ran. A running resource has no final cost
 * yet, so its rate is extrapolated to now instead.
 */
export const resourceCost = function (
    resource: CostResource,
    nowSeconds: number = Date.now() / 1000
): number | null {
    const info = resource?.instance_info;
    if (!info) return null;

    if (isKnownAmount(info.cost)) return info.cost;

    if (resource.state === RUNNING_STATE && isKnownAmount(info.price_per_hour) && isKnownAmount(info.creation_time)) {
        const elapsedHours = (nowSeconds - info.creation_time) / 3600;
        if (elapsedHours <= 0) return 0;
        return elapsedHours * info.price_per_hour;
    }

    return null;
};

/** True when the resource's cost is being extrapolated from its hourly rate right now. */
export const isLiveCost = function (resource: CostResource): boolean {
    const info = resource?.instance_info;
    if (!info) return false;
    return resource.state === RUNNING_STATE && !isKnownAmount(info.cost) && isKnownAmount(info.price_per_hour);
};

/** Sum the costs of every resource in a run, flagging the total as partial when any is unknown. */
export const runCostSummary = function (
    resources: CostResource[] | null | undefined,
    nowSeconds: number = Date.now() / 1000
): RunCostSummary {
    const summary: RunCostSummary = { total: 0, partial: false, known: 0, unknown: 0 };

    for (const resource of resources ?? []) {
        const cost = resourceCost(resource, nowSeconds);
        if (cost === null) {
            summary.unknown += 1;
        } else {
            summary.total += cost;
            summary.known += 1;
        }
    }

    summary.partial = summary.unknown > 0;
    return summary;
};

/** Render a USD amount, or `placeholder` when it is unknown. */
export const formatCost = function (cost: number | null | undefined, placeholder = "N/A"): string {
    if (typeof cost !== "number" || !Number.isFinite(cost)) return placeholder;
    return `$${cost.toFixed(2)}`;
};

/** Render an hourly rate, or `placeholder` when it is unknown. */
export const formatRate = function (rate: number | null | undefined, placeholder = "N/A"): string {
    if (!isKnownAmount(rate)) return placeholder;
    return `$${rate.toFixed(3)}/h`;
};
