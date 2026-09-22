import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, fireEvent, within } from "@testing-library/svelte";
import MultiStringValue from "./MultiStringValue.svelte";

afterEach(cleanup);

const DEFAULTS = ["dtest - release", "dtest - debug"];

const mount = (stored?: string[], dflt: string[] = []) => {
    const settings: Record<string, unknown> = {};
    if (stored !== undefined) settings.testFilters = stored;
    const result = render(MultiStringValue, {
        props: {
            settingName: "testFilters",
            definition: { displayName: "Test Filters", help: "help text", default: dflt },
            settings,
        },
    });
    return { ...result, settings };
};

const inputs = (container: HTMLElement) => container.querySelectorAll("input");

describe("MultiStringValue", () => {
    it("renders a row per stored entry", () => {
        const { container } = mount([".*/artifacts/", ".*/upgrade/"]);

        expect(inputs(container)).toHaveLength(2);
    });

    it("falls back to the definition default", () => {
        const { container, settings } = mount(undefined, DEFAULTS);

        expect(inputs(container)).toHaveLength(2);
        expect(settings.testFilters).toEqual(DEFAULTS);
    });

    it("never aliases the shared default array from the registry", async () => {
        const shared = [...DEFAULTS];
        const first = mount(undefined, shared);
        const second = mount(undefined, shared);

        await fireEvent.click(within(first.container).getByText(/Add Filter/));

        expect(shared).toEqual(DEFAULTS);
        expect(first.settings.testFilters).toHaveLength(3);
        expect(second.settings.testFilters).toHaveLength(2);
    });

    it("typing into a row updates the bound settings", async () => {
        const { container, settings } = mount([".*/artifacts/"]);

        await fireEvent.input(inputs(container)[0], { target: { value: "changed" } });

        expect(settings.testFilters).toEqual(["changed"]);
    });

    it("renders the new row immediately when one is added", async () => {
        const { container, getByText, settings } = mount([".*/artifacts/"]);

        await fireEvent.click(getByText(/Add Filter/));

        expect(inputs(container)).toHaveLength(2);
        expect(settings.testFilters).toEqual([".*/artifacts/", ""]);
    });

    it("drops the row from the markup immediately when one is removed", async () => {
        const { container, settings } = mount([".*/artifacts/", ".*/upgrade/"]);

        await fireEvent.click(within(container).queryAllByTitle("Remove this entry")[0]);

        expect(inputs(container)).toHaveLength(1);
        expect(settings.testFilters).toEqual([".*/upgrade/"]);
    });

    it("keeps the remaining row editable after a removal", async () => {
        const { container, settings } = mount([".*/artifacts/", ".*/upgrade/"]);

        await fireEvent.click(within(container).queryAllByTitle("Remove this entry")[0]);
        await fireEvent.input(inputs(container)[0], { target: { value: "still-bound" } });

        expect(settings.testFilters).toEqual(["still-bound"]);
    });
});
