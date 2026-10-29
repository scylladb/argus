import Chart from "chart.js/auto";
import type { ChartConfiguration } from "chart.js";

export function chart(canvas: HTMLCanvasElement, config: ChartConfiguration) {
    const instance = new Chart(canvas, config);
    return {
        update(next: ChartConfiguration) {
            instance.config.data = next.data;
            instance.config.options = next.options ?? {};
            instance.update();
        },
        destroy() {
            instance.destroy();
        },
    };
}
