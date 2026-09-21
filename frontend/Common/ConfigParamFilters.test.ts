import { describe, it, expect } from "vitest";
import {
    ANY_VALUE_LABEL,
    badgeLabel,
    configuredRows,
    emptyRow,
    hasDuplicateName,
    isRowActive,
    normalizeRows,
    toggleName,
} from "./ConfigParamFilters";

describe("normalizeRows", () => {
    it("returns nothing for a non-array", () => {
        expect(normalizeRows(undefined)).toEqual([]);
        expect(normalizeRows(null)).toEqual([]);
        expect(normalizeRows("sct_config.backend")).toEqual([]);
        expect(normalizeRows({ name: "sct_config.backend" })).toEqual([]);
    });

    it("keeps a concrete value and an any-value row apart", () => {
        expect(normalizeRows([
            { name: "sct_config.backend", value: "aws" },
            { name: "sct_config.unified_package", value: null },
        ])).toEqual([
            { name: "sct_config.backend", value: "aws" },
            { name: "sct_config.unified_package", value: null },
        ]);
    });

    it("reads a missing or blank value as any value", () => {
        expect(normalizeRows([{ name: "cfg.a" }, { name: "cfg.b", value: "" }])).toEqual([
            { name: "cfg.a", value: null },
            { name: "cfg.b", value: null },
        ]);
    });

    it("trims a name and drops a non-string one", () => {
        expect(normalizeRows([{ name: "  cfg.a  ", value: "x" }, { name: 7, value: "y" }])).toEqual([
            { name: "cfg.a", value: "x" },
            { name: "", value: "y" },
        ]);
    });

    it("skips a null entry", () => {
        expect(normalizeRows([null, { name: "cfg.a", value: "x" }])).toEqual([{ name: "cfg.a", value: "x" }]);
    });
});

describe("configuredRows", () => {
    it("drops a row with no name", () => {
        expect(configuredRows([{ name: "", value: "aws" }, { name: "cfg.a", value: null }])).toEqual([
            { name: "cfg.a", value: null },
        ]);
    });
});

describe("emptyRow", () => {
    it("returns a fresh object every call", () => {
        const first = emptyRow();
        const second = emptyRow();
        first.name = "cfg.a";

        expect(second).toEqual({ name: "", value: null });
        expect(first).not.toBe(second);
    });
});

describe("hasDuplicateName", () => {
    const rows = [{ name: "cfg.a", value: null }, { name: "cfg.b", value: "x" }];

    it("finds a repeat", () => {
        expect(hasDuplicateName(rows, "cfg.a")).toBe(true);
    });

    it("ignores the row being edited", () => {
        expect(hasDuplicateName(rows, "cfg.a", 0)).toBe(false);
    });

    it("never treats a blank name as a repeat", () => {
        expect(hasDuplicateName([{ name: "", value: null }], "")).toBe(false);
    });
});

describe("badgeLabel", () => {
    it("shows a concrete value", () => {
        expect(badgeLabel({ name: "cfg.backend", value: "aws" })).toBe("cfg.backend = aws");
    });

    it("labels an any-value row", () => {
        expect(badgeLabel({ name: "cfg.pkg", value: null })).toBe(`cfg.pkg = ${ANY_VALUE_LABEL}`);
    });
});

describe("isRowActive", () => {
    it("is active while its name is not switched off", () => {
        expect(isRowActive({ name: "cfg.a", value: null }, [])).toBe(true);
        expect(isRowActive({ name: "cfg.a", value: null }, ["cfg.b"])).toBe(true);
        expect(isRowActive({ name: "cfg.a", value: null }, ["cfg.a"])).toBe(false);
    });
});

describe("toggleName", () => {
    it("switches a name off and back on", () => {
        expect(toggleName([], "cfg.a")).toEqual(["cfg.a"]);
        expect(toggleName(["cfg.a"], "cfg.a")).toEqual([]);
    });

    it("returns a new array", () => {
        const off = ["cfg.a"];

        expect(toggleName(off, "cfg.b")).not.toBe(off);
        expect(off).toEqual(["cfg.a"]);
    });
});
