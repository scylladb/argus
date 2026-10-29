import type { Breakdown, ExplorerFilters, Granularity, Tier } from "./types";

export const DEFAULT_WINDOW_DAYS = 90;
export const RANGE_PRESETS = [7, 30, 90];
export const TIERS: Tier[] = ["spot", "on-demand"];
export const BREAKDOWNS: Breakdown[] = ["group", "test"];
export const GRANULARITIES: Granularity[] = ["day", "week", "month"];
export const LIST_KEYS = ["releaseNames", "groupIds", "testIds", "backends", "plugins", "statuses", "tiers"] as const;
export type ListKey = (typeof LIST_KEYS)[number];
const PARAM_OF: Record<ListKey, string> = {
    releaseNames: "releaseName",
    groupIds: "groupId",
    testIds: "testId",
    backends: "backend",
    plugins: "plugin",
    statuses: "status",
    tiers: "tier",
};
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

export const isoDate = (date: Date): string => date.toISOString().slice(0, 10);

export const daysAgo = (days: number, now: Date = new Date()): string => isoDate(new Date(now.getTime() - days * DAY_MS));

export function presetRange(days: number, now: Date = new Date()): { from: string; to: string } {
    return { from: daysAgo(days, now), to: isoDate(now) };
}

export function defaultFilters(now: Date = new Date()): ExplorerFilters {
    return {
        ...presetRange(DEFAULT_WINDOW_DAYS, now),
        releaseNames: [],
        groupIds: [],
        testIds: [],
        viewId: "",
        backends: [],
        plugins: [],
        statuses: [],
        tiers: [],
        breakdown: "group",
        granularity: "week",
    };
}

const oneOf = <T extends string>(value: string | null, allowed: T[], fallback: T): T =>
    allowed.includes(value as T) ? (value as T) : fallback;

const unique = (values: string[]): string[] => [...new Set(values.filter(Boolean))];

export function parseFilters(search: string, now: Date = new Date()): ExplorerFilters {
    const params = new URLSearchParams(search);
    const defaults = defaultFilters(now);
    const date = (key: "from" | "to") => {
        const value = params.get(key) ?? "";
        return DATE.test(value) ? value : defaults[key];
    };
    return {
        from: date("from"),
        to: date("to"),
        releaseNames: unique(params.getAll("releaseName")),
        groupIds: unique(params.getAll("groupId")),
        testIds: unique(params.getAll("testId")),
        viewId: params.get("viewId") ?? "",
        backends: unique(params.getAll("backend")),
        plugins: unique(params.getAll("plugin")),
        statuses: unique(params.getAll("status")),
        tiers: unique(params.getAll("tier")).filter((tier): tier is Tier => TIERS.includes(tier as Tier)),
        breakdown: oneOf(params.get("breakdown"), BREAKDOWNS, "group"),
        granularity: oneOf(params.get("granularity"), GRANULARITIES, "week"),
    };
}

export function serializeFilters(filters: ExplorerFilters): string {
    const params = new URLSearchParams();
    params.set("from", filters.from);
    params.set("to", filters.to);
    for (const key of LIST_KEYS) {
        for (const value of filters[key]) params.append(PARAM_OF[key], value);
    }
    if (filters.viewId) params.set("viewId", filters.viewId);
    if (filters.breakdown !== "group") params.set("breakdown", filters.breakdown);
    if (filters.granularity !== "week") params.set("granularity", filters.granularity);
    return params.toString();
}

export function apiParams(filters: ExplorerFilters): URLSearchParams {
    const params = new URLSearchParams(serializeFilters(filters));
    params.set("from", `${filters.from}T00:00:00Z`);
    const dayAfter = new Date(new Date(`${filters.to}T00:00:00Z`).getTime() + DAY_MS);
    params.set("to", `${isoDate(dayAfter)}T00:00:00Z`);
    params.set("breakdown", filters.breakdown);
    params.set("granularity", filters.granularity);
    return params;
}

export interface Span {
    from: string;
    to: string;
}

export function overlaps(filters: ExplorerFilters, span: Span): boolean {
    return isoDate(new Date(span.from)) <= filters.to && isoDate(new Date(span.to)) >= filters.from;
}

export function fitRange(span: Span): { from: string; to: string } {
    const last = new Date(span.to);
    const from = daysAgo(DEFAULT_WINDOW_DAYS, last);
    const first = isoDate(new Date(span.from));
    return { from: first > from ? first : from, to: isoDate(last) };
}
