import { isDarkTheme } from "./palette";

export function watchTheme() {
    let dark = $state(isDarkTheme());
    $effect(() => {
        if (typeof MutationObserver === "undefined") return;
        const observer = new MutationObserver(() => {
            dark = isDarkTheme();
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-bs-theme"] });
        return () => observer.disconnect();
    });
    return {
        get dark() {
            return dark;
        },
    };
}
