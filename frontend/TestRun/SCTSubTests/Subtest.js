import GeminiTabBodyComponent from "./Gemini/GeminiTabBodyComponent.svelte";
import PerformanceTabBodyComponent from "./Performance/PerformanceTabBodyComponent.svelte";

export const Subtests = {
    GEMINI: "gemini",
    PERFORMANCE: "performance",
};

export const SubtestTabMeta = {
    [Subtests.GEMINI]: { key: "gemini", label: "Gemini", faIcon: "faEye" },
    [Subtests.PERFORMANCE]: { key: "performance", label: "Performance", faIcon: "faChartSimple" },
};

export const SubtestTabBodyComponents = {
    [Subtests.GEMINI]: GeminiTabBodyComponent,
    [Subtests.PERFORMANCE]: PerformanceTabBodyComponent,
};
