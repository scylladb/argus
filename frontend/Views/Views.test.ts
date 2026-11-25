import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

vi.hoisted(() => {
    Object.assign(globalThis, { gArgusCurrentUser: {} });
});

import Views from "./Views.svelte";

const TAB_KEY = "viewsCurrentTab";

const tabButton = (name: string) => screen.getByRole("button", { name });

const isListShown = (emptyText: string) => !screen.getByText(emptyText).parentElement?.classList.contains("d-none");

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

describe("Views.svelte", () => {
    it("opens on the Automatic tab when no tab is saved", () => {
        render(Views, { props: { views: [] } });

        expect(tabButton("Automatic").classList.contains("active")).toBe(true);
        expect(tabButton("User-Generated").classList.contains("active")).toBe(false);
        expect(isListShown("No automatic views.")).toBe(true);
        expect(isListShown("No user-generated views.")).toBe(false);
    });

    it("opens on the saved tab", () => {
        window.localStorage.setItem(TAB_KEY, "1");

        render(Views, { props: { views: [] } });

        expect(tabButton("User-Generated").classList.contains("active")).toBe(true);
        expect(isListShown("No user-generated views.")).toBe(true);
        expect(isListShown("No automatic views.")).toBe(false);
    });

    it("switches to the clicked tab and saves it", async () => {
        render(Views, { props: { views: [] } });

        await fireEvent.click(tabButton("Favorite"));

        expect(tabButton("Favorite").classList.contains("active")).toBe(true);
        expect(tabButton("Automatic").classList.contains("active")).toBe(false);
        expect(isListShown("No favorite views.")).toBe(true);
        expect(isListShown("No automatic views.")).toBe(false);
        expect(window.localStorage.getItem(TAB_KEY)).toBe("2");
    });
});
