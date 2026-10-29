import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

import ScreenshotModal from "./ScreenshotModal.svelte";

const SHOTS = ["a.png", "b.png", "c.png"].map((name) => `/api/v1/tests/sct/run-1/screenshot/${name}`);

const key = (name: string) => fireEvent.keyDown(document.body, { key: name });

const dialog = () => screen.queryByRole("dialog", { name: "Screenshot viewer" });

const image = () => screen.getByAltText("Screenshot") as HTMLImageElement;

const scaleOf = () => Number(/scale\(([^)]+)\)/.exec(image().style.transform)?.[1]);

const layOut = () => {
    const img = image();
    const stage = img.parentElement as HTMLElement;
    for (const [name, value] of Object.entries({ clientWidth: 1000, clientHeight: 800 })) {
        Object.defineProperty(stage, name, { configurable: true, value });
    }
    for (const [name, value] of Object.entries({ offsetWidth: 1000, offsetHeight: 562.5, naturalWidth: 1920 })) {
        Object.defineProperty(img, name, { configurable: true, value });
    }
};

afterEach(() => {
    cleanup();
    document.body.className = "";
    document.body.innerHTML = "";
});

describe("ScreenshotModal.svelte", () => {
    it("renders nothing while no screenshot is selected", () => {
        render(ScreenshotModal, { props: { selectedScreenshot: "", screenshots: SHOTS } });

        expect(dialog()).toBeNull();
    });

    it("shows the selected screenshot with its place in the list", () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[1], screenshots: SHOTS } });

        expect(image().src).toContain(SHOTS[1]);
        expect(screen.getByText("2 / 3")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Previous screenshot" })).toBeTruthy();
        expect(screen.getByRole("link", { name: "Open original" }).getAttribute("href")).toBe(SHOTS[1]);
    });

    it("shows a single URL without a counter or arrows", () => {
        render(ScreenshotModal, { props: { selectedScreenshot: "https://bucket.s3.amazonaws.com/shot.png" } });

        expect(image().src).toBe("https://bucket.s3.amazonaws.com/shot.png");
        expect(screen.queryByText(/\/ /)).toBeNull();
        expect(screen.queryByRole("button", { name: "Previous screenshot" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Next screenshot" })).toBeNull();
    });

    it("closes on Escape", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });

        await key("Escape");

        expect(dialog()).toBeNull();
    });

    it("moves through the list with the arrow keys and resets the zoom", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });
        layOut();
        await key("+");
        expect(scaleOf()).toBeCloseTo(1.25, 10);

        await key("ArrowRight");
        expect(image().src).toContain(SHOTS[1]);
        expect(screen.getByText("2 / 3")).toBeTruthy();
        expect(scaleOf()).toBeCloseTo(1, 10);

        await key("ArrowLeft");
        expect(image().src).toContain(SHOTS[0]);
        expect(screen.getByText("1 / 3")).toBeTruthy();
    });

    it("disables previous on the first screenshot and next on the last", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });

        const previous = screen.getByRole("button", { name: "Previous screenshot" }) as HTMLButtonElement;
        const next = screen.getByRole("button", { name: "Next screenshot" }) as HTMLButtonElement;
        expect(previous.disabled).toBe(true);
        expect(next.disabled).toBe(false);

        await fireEvent.click(next);
        await fireEvent.click(screen.getByRole("button", { name: "Next screenshot" }));

        expect(image().src).toContain(SHOTS[2]);
        expect((screen.getByRole("button", { name: "Next screenshot" }) as HTMLButtonElement).disabled).toBe(true);
        expect((screen.getByRole("button", { name: "Previous screenshot" }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("zooms with the keys and the buttons and returns to fit", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });
        layOut();

        await key("+");
        await key("=");
        expect(scaleOf()).toBeCloseTo(1.5625, 10);

        await key("-");
        expect(scaleOf()).toBeCloseTo(1.25, 10);

        await key("1");
        expect(scaleOf()).toBeCloseTo(1.92, 10);

        await key("0");
        expect(scaleOf()).toBeCloseTo(1, 10);

        await fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
        expect(scaleOf()).toBeCloseTo(1.25, 10);

        await fireEvent.click(screen.getByRole("button", { name: "Fit to window" }));
        expect(scaleOf()).toBeCloseTo(1, 10);
    });

    it("leaves a key with a modifier to the browser", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });
        layOut();
        await key("+");

        await fireEvent.keyDown(document.body, { key: "ArrowRight", altKey: true });
        await fireEvent.keyDown(document.body, { key: "0", ctrlKey: true });

        expect(image().src).toContain(SHOTS[0]);
        expect(scaleOf()).toBeCloseTo(1.25, 10);
    });

    it("ignores the shortcuts while closed", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: "", screenshots: SHOTS } });

        await key("ArrowRight");
        await key("+");

        expect(dialog()).toBeNull();
    });

    it("takes the focus on open and gives it back to the trigger on close", async () => {
        const trigger = document.createElement("button");
        document.body.append(trigger);
        trigger.focus();
        const { rerender } = render(ScreenshotModal, { props: { selectedScreenshot: "", screenshots: SHOTS } });

        await rerender({ selectedScreenshot: SHOTS[0], screenshots: SHOTS });
        expect(document.activeElement).toBe(dialog());

        await key("Escape");
        expect(document.activeElement).toBe(trigger);
    });

    it("locks the page scroll while open", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });
        expect(document.body.classList.contains("overflow-hidden")).toBe(true);

        await fireEvent.click(screen.getByRole("button", { name: "Close" }));

        expect(document.body.classList.contains("overflow-hidden")).toBe(false);
    });

    it("says so and keeps the original link when the image fails to load", async () => {
        render(ScreenshotModal, { props: { selectedScreenshot: SHOTS[0], screenshots: SHOTS } });

        await fireEvent.error(image());

        expect(screen.getByText("The screenshot could not be loaded.")).toBeTruthy();
        expect(screen.getByRole("link", { name: "Open the original" }).getAttribute("href")).toBe(SHOTS[0]);
        expect(screen.queryByAltText("Screenshot")).toBeNull();

        await key("ArrowRight");
        expect(image().src).toContain(SHOTS[1]);
        expect(screen.queryByText("The screenshot could not be loaded.")).toBeNull();
    });
});
