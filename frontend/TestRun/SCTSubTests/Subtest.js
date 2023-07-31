import GeminiTabBodyComponent from "./Gemini/GeminiTabBodyComponent.svelte";
import GeminiTabComponent from "./Gemini/GeminiTabComponent.svelte";
import PerformanceTabBodyComponent from "./Performance/PerformanceTabBodyComponent.svelte";
import PerformanceTabComponent from "./Performance/PerformanceTabComponent.svelte";

export const Subtests = {
    GEMINI: "gemini",
    PERFORMANCE: "performance",
};

export const SubtestTabComponents = {
    [Subtests.GEMINI]: GeminiTabComponent,
    [Subtests.PERFORMANCE]: PerformanceTabComponent,
};

export const SubtestTabBodyComponents = {
    [Subtests.GEMINI]: GeminiTabBodyComponent,
    [Subtests.PERFORMANCE]: PerformanceTabBodyComponent,
};
