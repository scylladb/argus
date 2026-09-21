import sha1 from "js-sha1";
import { configuredRows } from "./ConfigParamFilters";

// sha1("")
export const GLOBAL_STATS_KEY = "da39a3ee5e6b4b0d3255bfef95601890afd80709";

export const calculateWidgetVersionKey = function (widget): string {
    return sha1((widget.filter ?? []).join(""));
};

export const calculateWidgetStatsKey = function (widget): string {
    const base = (widget.filter ?? []).join("");
    const narrowed = configuredRows(widget.settings?.configParamFilters).length > 0;
    return sha1(narrowed ? `${base}#${widget.position}` : base);
};
