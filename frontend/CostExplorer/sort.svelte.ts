export type SortDirection = "asc" | "desc";
export type SortValue = number | string | null | undefined;

export function createSort<K extends string>(initialKey: K, initialDirection: SortDirection = "desc") {
    let key = $state(initialKey);
    let direction = $state(initialDirection);

    const compare = (lhs: SortValue, rhs: SortValue): number => {
        if (lhs === rhs) return 0;
        if (lhs === null || lhs === undefined) return 1;
        if (rhs === null || rhs === undefined) return -1;
        if (typeof lhs === "number" && typeof rhs === "number") return lhs - rhs;
        return String(lhs).localeCompare(String(rhs), undefined, { sensitivity: "base", numeric: true });
    };

    return {
        get key() {
            return key;
        },
        get direction() {
            return direction;
        },
        toggle(next: K, defaultDirection: SortDirection = "desc") {
            if (key === next) {
                direction = direction === "asc" ? "desc" : "asc";
            } else {
                key = next;
                direction = defaultDirection;
            }
        },
        apply<T>(rows: T[], value: (row: T, by: K) => SortValue): T[] {
            const sign = direction === "asc" ? 1 : -1;
            return [...rows].sort((lhs, rhs) => sign * compare(value(lhs, key), value(rhs, key)));
        },
    };
}

export type Sort<K extends string> = ReturnType<typeof createSort<K>>;
