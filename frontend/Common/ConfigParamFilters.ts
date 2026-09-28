export const ANY_VALUE_LABEL = "(any value)";

export interface ConfigParamFilterRow {
    name: string;
    value: string | null;
}

export const emptyRow = (): ConfigParamFilterRow => ({ name: "", value: null });

// parse_config_values stores Python's str(value), so a boolean lands as "True"/"False".
// Matching that here keeps a value set through the API or the CLI filtering the same runs
// after the editor has opened and saved the view.
export const asStoredValue = (value: unknown): string | null => {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value === "boolean") return value ? "True" : "False";
    if (typeof value === "object") return null;
    return String(value);
};

export const normalizeRows = (raw: unknown): ConfigParamFilterRow[] => {
    if (!Array.isArray(raw)) return [];
    return raw
        .filter((row): row is Record<string, unknown> => !!row && typeof row === "object")
        .map((row) => ({
            name: typeof row.name === "string" ? row.name.trim() : "",
            value: asStoredValue(row.value),
        }));
};

export const configuredRows = (rows: unknown): ConfigParamFilterRow[] =>
    normalizeRows(rows).filter((row) => row.name !== "");

export const hasDuplicateName = (rows: ConfigParamFilterRow[], name: string, ignoreIndex = -1): boolean =>
    rows.some((row, idx) => idx !== ignoreIndex && row.name !== "" && row.name === name);

export const badgeLabel = (row: ConfigParamFilterRow): string =>
    `${row.name} = ${row.value ?? ANY_VALUE_LABEL}`;

export const isRowActive = (row: ConfigParamFilterRow, offNames: string[]): boolean =>
    !offNames.includes(row.name);

export const toggleName = (offNames: string[], name: string): string[] =>
    offNames.includes(name) ? offNames.filter((n) => n !== name) : [...offNames, name];
