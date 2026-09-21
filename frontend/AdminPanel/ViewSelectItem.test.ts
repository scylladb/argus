import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import ViewSelectItem from "./ViewSelectItem.svelte";

afterEach(cleanup);

const TEST_HIT = {
    id: "t-1",
    name: "longevity-10gb-3h-test",
    type: "test",
    test_metadata: { tier: "tier1", description: "Basic longevity test." },
};

const GROUP_HIT = {
    id: "g-1",
    name: "longevity",
    type: "group",
    test_metadata: { tier: "tier1" },
};

describe("ViewSelectItem", () => {
    it("renders the metadata of a test hit", () => {
        const { container } = render(ViewSelectItem, { item: TEST_HIT });

        expect(container.textContent).toContain("tier1");
        expect(container.textContent).toContain("Basic longevity test.");
    });

    it("renders no metadata for a group hit", () => {
        const { container } = render(ViewSelectItem, { item: GROUP_HIT });

        expect(container.querySelectorAll(".badge")).toHaveLength(0);
    });

    it("renders a test hit that carries no metadata", () => {
        const { container } = render(ViewSelectItem, { item: { ...TEST_HIT, test_metadata: {} } });

        expect(container.textContent).toContain("longevity-10gb-3h-test");
        expect(container.querySelectorAll(".badge")).toHaveLength(0);
    });
});
