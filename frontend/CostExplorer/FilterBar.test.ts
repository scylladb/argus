import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/svelte";

vi.hoisted(() => {
    window.matchMedia = (query: string) =>
        ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
           addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }) as unknown as MediaQueryList;
    Element.prototype.getAnimations = () => [];
});
vi.mock("./api", () => ({
    displayName: (entity: { name: string }) => entity.name,
    loadReleases: vi.fn(async () => [{ id: "release-1", name: "2026.1" }]),
    loadGroups: vi.fn(async () => [{ id: "group-1", name: "longevity" }]),
    loadTests: vi.fn(async () => [{ id: "test-1", name: "longevity-100gb" }]),
}));

import FilterBar from "./FilterBar.svelte";
import { defaultFilters } from "./filters";

afterEach(cleanup);

describe("FilterBar.svelte", () => {
    it("drops the group and test filters once no release is selected", async () => {
        const filters = { ...defaultFilters(), groupIds: ["group-1"], testIds: ["test-1"] };

        render(FilterBar, { props: { filters } });

        await waitFor(() => expect(filters.groupIds).toEqual([]));
        await waitFor(() => expect(filters.testIds).toEqual([]));
    });

    it("keeps the group and test filters while a release is selected", async () => {
        const filters = { ...defaultFilters(), releaseNames: ["2026.1"], groupIds: ["group-1"], testIds: ["test-1"] };

        render(FilterBar, { props: { filters } });
        await new Promise((resolve) => setTimeout(resolve, 0));

        expect(filters.groupIds).toEqual(["group-1"]);
        expect(filters.testIds).toEqual(["test-1"]);
    });
});
