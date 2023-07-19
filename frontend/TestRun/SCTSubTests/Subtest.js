import GeminiTabBodyComponent from "./Gemini/GeminiTabBodyComponent.svelte";
import GeminiTabComponent from "./Gemini/GeminiTabComponent.svelte";

export const Subtests = {
    GEMINI: "gemini",
};

export const SubtestTabComponents = {
    [Subtests.GEMINI]: GeminiTabComponent,
};

export const SubtestTabBodyComponents = {
    [Subtests.GEMINI]: GeminiTabBodyComponent,
};
