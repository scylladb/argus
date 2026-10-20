import { NemesisStatusBg, NemesisStatusFg } from "../../Common/TestStatus";
import { timestampToISODate } from "../../Common/DateUtils";
import { titleCase } from "../../Common/TextUtils";
import type { NemesisInfo } from "./types";

export type SortKey = "name" | "node" | "status" | "start_time" | "end_time";
export type SortDirection = "asc" | "desc";

export interface SortState {
    key: SortKey;
    direction: SortDirection;
}

const DEFAULT_DIRECTION: Record<SortKey, SortDirection> = {
    name: "asc",
    node: "asc",
    status: "asc",
    start_time: "desc",
    end_time: "desc",
};

export const DEFAULT_SORT: SortState = { key: "start_time", direction: "desc" };

const STATUS_BACKGROUNDS = NemesisStatusBg as Record<string, string>;
const STATUS_FOREGROUNDS = NemesisStatusFg as Record<string, string>;

export const nemesisKey = (nemesis: NemesisInfo): string => `${nemesis.start_time}:${nemesis.name}`;

export const statusLabel = (status: string): string => (status ? titleCase(status) : "Unknown");

export const statusClasses = (status: string): string =>
    `${STATUS_BACKGROUNDS[status] ?? "bg-secondary"} ${STATUS_FOREGROUNDS[status] ?? "text-light"}`;

export const formatNemesisTime = (seconds: number): string => timestampToISODate(seconds * 1000, true);

export const endTimeLabel = (nemesis: NemesisInfo): string =>
    nemesis.end_time === 0 ? "In progress" : formatNemesisTime(nemesis.end_time);

export const descriptionSummary = (description: string | null | undefined): string =>
    description?.split("\n").map((line) => line.trim()).find(Boolean) ?? "";

export const reasonLabel = (status: string): string => {
    switch (status) {
    case "skipped":
        return "Skip reason";
    case "failed":
        return "Failure reason";
    default:
        return "Message";
    }
};

export const nextSort = (current: SortState, key: SortKey): SortState =>
    current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: DEFAULT_DIRECTION[key] };

const compareText = (left: string, right: string): number => left.localeCompare(right, undefined, { numeric: true });

const endOrder = (nemesis: NemesisInfo): number => (nemesis.end_time === 0 ? Number.MAX_SAFE_INTEGER : nemesis.end_time);

const compareBy = (key: SortKey, left: NemesisInfo, right: NemesisInfo): number => {
    switch (key) {
    case "name":
        return compareText(left.name, right.name);
    case "node":
        return compareText(left.target_node.name, right.target_node.name);
    case "status":
        return compareText(left.status, right.status);
    case "start_time":
        return left.start_time - right.start_time;
    case "end_time":
        return endOrder(left) - endOrder(right);
    }
};

export const sortNemeses = (nemeses: readonly NemesisInfo[], sort: SortState): NemesisInfo[] => {
    const sign = sort.direction === "asc" ? 1 : -1;
    return nemeses.toSorted(
        (left, right) =>
            sign * compareBy(sort.key, left, right) ||
            left.start_time - right.start_time ||
            compareText(left.name, right.name)
    );
};

const searchText = (nemesis: NemesisInfo): string =>
    [
        nemesis.name,
        nemesis.class_name,
        nemesis.target_node.name,
        statusLabel(nemesis.status),
        formatNemesisTime(nemesis.start_time),
        endTimeLabel(nemesis),
        nemesis.description ?? "",
    ].join("\n");

export const nemesisMatches = (nemesis: NemesisInfo, filter: string): boolean => {
    const pattern = filter.trim();
    if (!pattern) {
        return true;
    }
    const text = searchText(nemesis);
    try {
        return new RegExp(pattern, "i").test(text);
    } catch {
        return text.toLowerCase().includes(pattern.toLowerCase());
    }
};

export const filterNemeses = (nemeses: readonly NemesisInfo[], filter: string): NemesisInfo[] =>
    nemeses.filter((nemesis) => nemesisMatches(nemesis, filter));
