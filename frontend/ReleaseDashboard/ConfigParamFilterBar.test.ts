import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import ConfigParamFilterBar from "./ConfigParamFilterBar.svelte";
import { ANY_VALUE_LABEL } from "../Common/ConfigParamFilters";

const ROWS = [
    { name: "sct_config.unified_package", value: null },
    { name: "sct_config.backend", value: "aws" },
];

afterEach(cleanup);

describe("ConfigParamFilterBar", () => {
    it("renders one badge per configured row", () => {
        const { getAllByRole } = render(ConfigParamFilterBar, { props: { rows: ROWS } });

        expect(getAllByRole("button")).toHaveLength(2);
    });

    it("labels an any-value row and a concrete one", () => {
        const { getByText } = render(ConfigParamFilterBar, { props: { rows: ROWS } });

        expect(getByText(`sct_config.unified_package = ${ANY_VALUE_LABEL}`)).toBeTruthy();
        expect(getByText("sct_config.backend = aws")).toBeTruthy();
    });

    it("reports the row name on click", async () => {
        const toggled: string[] = [];
        const { getByText } = render(ConfigParamFilterBar, {
            props: { rows: ROWS, ontoggle: (name: string) => toggled.push(name) },
        });

        await fireEvent.click(getByText("sct_config.backend = aws"));

        expect(toggled).toEqual(["sct_config.backend"]);
    });

    it("renders a switched-off badge muted and an active one not", () => {
        const { getByText } = render(ConfigParamFilterBar, {
            props: { rows: ROWS, offNames: ["sct_config.backend"] },
        });

        expect(getByText("sct_config.backend = aws").className).toContain("param-badge-off");
        expect(getByText(`sct_config.unified_package = ${ANY_VALUE_LABEL}`).className).toContain("param-badge-on");
    });

    it("renders nothing but the caption when no row is configured", () => {
        const { queryAllByRole } = render(ConfigParamFilterBar, { props: { rows: [] } });

        expect(queryAllByRole("button")).toHaveLength(0);
    });
});
