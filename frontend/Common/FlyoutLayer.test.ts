import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/svelte";
import FlyoutLayer from "./FlyoutLayer.svelte";

afterEach(cleanup);

describe("FlyoutLayer.svelte", () => {
    it("shows each flight with its label and reports the landing", async () => {
        const onLanded = vi.fn();

        render(FlyoutLayer, {
            props: { flights: [{ id: 1, from: { x: 10, y: 20 }, to: { x: 900, y: 600 }, label: "longevity-100gb-4h" }], onLanded },
        });

        expect(screen.getByText("longevity-100gb-4h")).toBeTruthy();
        await waitFor(() => expect(onLanded).toHaveBeenCalledWith(1));
    });

    it("starts each flight at the cursor", () => {
        render(FlyoutLayer, {
            props: { flights: [{ id: 2, from: { x: 10, y: 20 }, to: { x: 900, y: 600 }, label: "gemini" }], onLanded: vi.fn() },
        });

        const anchor = screen.getByText("gemini").closest(".flyout-anchor") as HTMLElement;
        expect(anchor.style.transform).toBe("translate(10px, 20px)");
    });
});
