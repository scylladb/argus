import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

import Screenshots from "./Screenshots.svelte";

const TEST_INFO = { test: { plugin_name: "scylla-cluster-tests" } };
const LINKS = ["grafana-1.png", "grafana-2.png", "grafana-3.png"].map((name) => `https://bucket.s3.amazonaws.com/run-1/${name}`);
const URLS = ["grafana-1.png", "grafana-2.png", "grafana-3.png"].map((name) => `/api/v1/tests/scylla-cluster-tests/run-1/screenshot/${name}`);

const renderGallery = (screenshots: string[] = LINKS) => render(Screenshots, { props: { screenshots, testInfo: TEST_INFO, runId: "run-1" } });

const thumbs = () => screen.getAllByRole("button", { name: /^Screenshot \d$/ });

const shown = () => (screen.getByAltText("Screenshot") as HTMLImageElement).getAttribute("src");

afterEach(() => {
    cleanup();
    document.body.className = "";
});

describe("Screenshots.svelte", () => {
    it("renders a numbered button per screenshot with the proxied image", () => {
        renderGallery();

        const images = thumbs().map((thumb) => thumb.querySelector("img") as HTMLImageElement);
        expect(images.map((img) => img.getAttribute("src"))).toEqual(URLS);
        expect(images.map((img) => img.getAttribute("alt"))).toEqual(["Screenshot 1", "Screenshot 2", "Screenshot 3"]);
        expect(images.every((img) => img.getAttribute("loading") === "lazy")).toBe(true);
    });

    it("says that no screenshot was submitted", () => {
        renderGallery([]);

        expect(screen.getByText("No screenshots submitted!")).toBeTruthy();
        expect(screen.queryByRole("button")).toBeNull();
    });

    it("opens the viewer on the clicked screenshot and moves through the gallery", async () => {
        renderGallery();

        await fireEvent.click(screen.getByRole("button", { name: "Screenshot 2" }));

        expect(screen.getByRole("dialog", { name: "Screenshot viewer" })).toBeTruthy();
        expect(shown()).toBe(URLS[1]);
        expect(screen.getByText("2 / 3")).toBeTruthy();

        await fireEvent.keyDown(document.body, { key: "ArrowRight" });
        expect(shown()).toBe(URLS[2]);
    });

    it("returns the focus to the thumbnail that opened the viewer", async () => {
        renderGallery();
        const thumb = screen.getByRole("button", { name: "Screenshot 1" });
        thumb.focus();

        await fireEvent.click(thumb);
        expect(document.activeElement).toBe(screen.getByRole("dialog", { name: "Screenshot viewer" }));

        await fireEvent.keyDown(document.body, { key: "Escape" });
        expect(document.activeElement).toBe(thumb);
    });
});
