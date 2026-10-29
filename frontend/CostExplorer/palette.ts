// Categorical slots validated for adjacent-pair color-vision separation on the
// light and the dark surface; the order is the safety mechanism, so it is fixed.
const LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const OTHER = { light: "#8a8884", dark: "#9b9a95" };

export const BACKEND_ORDER = ["aws", "gce", "azure", "xcloud", "k8s-eks", "k8s-gke", "oci", "docker"];

export const isDarkTheme = (): boolean =>
    typeof document !== "undefined" && document.documentElement.getAttribute("data-bs-theme") === "dark";

export function orderedBackends(backends: string[]): string[] {
    const known = BACKEND_ORDER.filter((backend) => backends.includes(backend));
    const rest = backends.filter((backend) => !BACKEND_ORDER.includes(backend)).sort();
    return [...known, ...rest];
}

export function seriesColor(backend: string, position: number, dark: boolean): string {
    const slots = dark ? DARK : LIGHT;
    if (position >= slots.length || backend === "unknown") return dark ? OTHER.dark : OTHER.light;
    return slots[position];
}

export const COVERAGE_COLORS = {
    light: { complete: LIGHT[0], partial: LIGHT[1], none: OTHER.light },
    dark: { complete: DARK[0], partial: DARK[1], none: OTHER.dark },
};

export const TIER_COLORS = {
    light: { spot: LIGHT[2], on_demand: LIGHT[0], untiered: OTHER.light },
    dark: { spot: DARK[2], on_demand: DARK[0], untiered: OTHER.dark },
};
