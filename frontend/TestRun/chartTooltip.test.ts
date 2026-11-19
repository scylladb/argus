import { describe, it, expect, vi, afterEach } from "vitest";

import { tooltipAnchor } from "./chartTooltip";

const rect = (left: number, top: number) => ({ left, top, x: left, y: top, width: 0, height: 0, right: left, bottom: top, toJSON: () => ({}) }) as DOMRect;

afterEach(() => {
    vi.restoreAllMocks();
    document.body.replaceChildren();
});

describe("tooltipAnchor", () => {
    it("anchors to the body in page coordinates", () => {
        const canvas = document.createElement("canvas");
        document.body.append(canvas);
        vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(rect(100, 50));
        vi.spyOn(window, "scrollX", "get").mockReturnValue(10);
        vi.spyOn(window, "scrollY", "get").mockReturnValue(300);

        expect(tooltipAnchor(canvas, 7, 9)).toEqual({ host: document.body, left: 117, top: 359 });
    });

    it("anchors to the enclosing dialog with its scroll offset", () => {
        const dialog = document.createElement("dialog");
        const box = document.createElement("div");
        const canvas = document.createElement("canvas");
        box.append(canvas);
        dialog.append(box);
        document.body.append(dialog);
        vi.spyOn(dialog, "getBoundingClientRect").mockReturnValue(rect(0, 0));
        vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(rect(200, 80));
        dialog.scrollTop = 400;
        vi.spyOn(window, "scrollY", "get").mockReturnValue(300);

        expect(tooltipAnchor(canvas, 7, 9)).toEqual({ host: dialog, left: 207, top: 489 });
    });
});
