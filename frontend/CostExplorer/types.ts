export type Tier = "spot" | "on-demand";
export type Breakdown = "group" | "test";
export type Granularity = "day" | "week" | "month";
export type Coverage = "complete" | "partial" | "none";

export interface ExplorerFilters {
    from: string;
    to: string;
    releaseNames: string[];
    groupIds: string[];
    testIds: string[];
    viewId: string;
    backends: string[];
    plugins: string[];
    statuses: string[];
    tiers: Tier[];
    breakdown: Breakdown;
    granularity: Granularity;
}

export interface Tiles {
    spend: number;
    previous_spend: number;
    weekly_run_rate: number;
    errored_spend: number;
    leaked_spend: number;
    leaked_count: number;
    runs: number;
    priced_runs: number;
}

export interface Series {
    buckets: string[];
    backends: Record<string, number[]>;
}

export interface BreakdownRow {
    id: string | null;
    name: string;
    runs: number;
    priced_runs: number;
    spend: number;
    cost_per_run: number | null;
}

export interface ReleaseEntry {
    id: string;
    name: string;
    runs: number;
    priced_runs: number;
    spend: number;
    rows: BreakdownRow[];
}

export interface TopRun {
    run_id: string;
    build_id: string;
    build_number: number | null;
    plugin_name: string;
    release: string;
    group: string;
    test: string;
    status: string;
    start_time: string;
    end_time: string | null;
    backend: string | null;
    region: string | null;
    spend: number;
    coverage: Coverage;
    spot_terminated: boolean;
}

export interface CoverageCounts {
    complete: number;
    partial: number;
    none: number;
    estimate_only: { count: number; spend: number };
}

export interface TierSplit {
    spend: number;
    items: number;
}

export interface SpotLocation {
    backend: string | null;
    region: string | null;
    count: number;
    spend: number;
}

export interface SpotTerminations {
    count: number;
    spot_runs: number;
    rate: number;
    spend: number;
    by_location: SpotLocation[];
}

export interface ExplorerResponse {
    window: { from: string; to: string; granularity: Granularity; breakdown: Breakdown; tiers: Tier[] };
    span: { from: string; to: string } | null;
    tiles: Tiles;
    series: Series;
    releases: ReleaseEntry[];
    top_runs: TopRun[];
    coverage: CoverageCounts;
    tiers: { spot: TierSplit; on_demand: TierSplit; untiered: TierSplit };
    spot_terminations: SpotTerminations;
}

export interface NamedEntity {
    id: string;
    name: string;
    pretty_name?: string | null;
}
