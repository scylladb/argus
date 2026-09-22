import { describe, it, expect, afterEach, beforeAll, vi } from "vitest";
import { render, cleanup, fireEvent, within } from "@testing-library/svelte";
import ConfigParamFilterValue from "./ConfigParamFilterValue.svelte";
import { ANY_VALUE_LABEL } from "../../Common/ConfigParamFilters";

// The two Selects call loadOptions against the search endpoints on any input.
beforeAll(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ json: () => Promise.resolve({ status: "ok", response: [] }) }),
    );
});

afterEach(cleanup);

const DEFINITION = { displayName: "Config Parameter Filters", help: "help text", default: [] };

const mount = (stored?: unknown) => {
    const settings: Record<string, unknown> = {};
    if (stored !== undefined) settings.configParamFilters = stored;
    const result = render(ConfigParamFilterValue, {
        props: { settingName: "configParamFilters", definition: DEFINITION, settings },
    });
    return { ...result, settings };
};

describe("ConfigParamFilterValue", () => {
    it("starts with no rows and an add button", () => {
        const { getByText, settings } = mount();

        expect(getByText(/Add Parameter Filter/)).toBeTruthy();
        expect(settings.configParamFilters).toEqual([]);
    });

    it("never shares the registry default array between two editors", () => {
        const first = mount();
        const second = mount();

        expect(first.settings.configParamFilters).not.toBe(DEFINITION.default);
        expect(first.settings.configParamFilters).not.toBe(second.settings.configParamFilters);
        expect(DEFINITION.default).toEqual([]);
    });

    it("adds a row without touching the other editor", async () => {
        const first = mount();
        const second = mount();

        await fireEvent.click(within(first.container).getByText(/Add Parameter Filter/));

        expect(first.settings.configParamFilters).toHaveLength(1);
        expect(second.settings.configParamFilters).toHaveLength(0);
        expect(DEFINITION.default).toEqual([]);
    });

    it("renders a stored row, showing an any-value row as such", () => {
        const { getByText } = mount([{ name: "sct_config.unified_package", value: null }]);

        expect(getByText(ANY_VALUE_LABEL)).toBeTruthy();
    });

    it("normalizes a stored row with a blank value into an any-value row", () => {
        const { settings } = mount([{ name: "cfg.a", value: "" }]);

        expect(settings.configParamFilters).toEqual([{ name: "cfg.a", value: null }]);
    });

    it("renders the new row immediately, without a remount", async () => {
        const { container, getByText } = mount();

        expect(within(container).queryAllByTitle("Remove this filter")).toHaveLength(0);

        await fireEvent.click(getByText(/Add Parameter Filter/));
        expect(within(container).queryAllByTitle("Remove this filter")).toHaveLength(1);

        await fireEvent.click(getByText(/Add Parameter Filter/));
        expect(within(container).queryAllByTitle("Remove this filter")).toHaveLength(2);
    });

    it("drops the removed row from the markup immediately", async () => {
        const { container } = mount([{ name: "cfg.a", value: "x" }, { name: "cfg.b", value: "y" }]);

        await fireEvent.click(within(container).queryAllByTitle("Remove this filter")[0]);

        expect(within(container).queryAllByTitle("Remove this filter")).toHaveLength(1);
    });

    it("shows the chosen parameter name in the select", () => {
        const { container } = mount([{ name: "sct_config.backend", value: "aws" }]);

        expect(container.querySelector(".selected-item")?.textContent).toContain("sct_config.backend");
    });

    it("leaves the select input unstyled so the selection stays visible", () => {
        // svelte-select's input is absolutely positioned over .selected-item; an opaque
        // background such as Bootstrap's .form-control hides the chosen value.
        const { container } = mount([{ name: "cfg.a", value: "x" }]);

        for (const input of container.querySelectorAll(".svelte-select input")) {
            expect(input.className).not.toContain("form-control");
        }
    });

    it("removes a row", async () => {
        const { getByTitle, settings } = mount([{ name: "cfg.a", value: "x" }]);

        await fireEvent.click(getByTitle("Remove this filter"));

        expect(settings.configParamFilters).toEqual([]);
    });

    it("toggles a row between any-value and a concrete value", async () => {
        const { getByText, settings } = mount([{ name: "cfg.a", value: "x" }]);

        await fireEvent.click(getByText("Any"));
        expect(settings.configParamFilters).toEqual([{ name: "cfg.a", value: null }]);

        await fireEvent.click(getByText("Any"));
        expect(settings.configParamFilters).toEqual([{ name: "cfg.a", value: "" }]);
    });

    it("leaves the Any toggle disabled until a parameter is chosen", () => {
        const { getByText } = mount([{ name: "", value: "" }]);

        expect((getByText("Any") as HTMLButtonElement).disabled).toBe(true);
    });
});
