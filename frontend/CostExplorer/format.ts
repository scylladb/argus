const whole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const count = new Intl.NumberFormat("en-US");

export const usd = (amount: number | null | undefined): string => {
    if (amount === null || amount === undefined) return "No data";
    return Math.abs(amount) >= 1000 ? whole.format(amount) : cents.format(amount);
};

export const integer = (value: number): string => count.format(value);

export const percent = (ratio: number, digits = 1): string => `${(ratio * 100).toFixed(digits)}%`;

export const share = (part: number, total: number): string => (total > 0 ? percent(part / total) : "0%");

export interface Trend {
    direction: "up" | "down" | "flat";
    ratio: number | null;
}

export const trend = (current: number, previous: number): Trend => {
    if (previous <= 0) return { direction: "flat", ratio: null };
    const ratio = (current - previous) / previous;
    if (Math.abs(ratio) < 0.005) return { direction: "flat", ratio };
    return { direction: ratio > 0 ? "up" : "down", ratio };
};

export const duration = (start: string, end: string | null): string => {
    if (!end) return "—";
    const minutes = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000);
    if (minutes < 0) return "—";
    const hours = Math.floor(minutes / 60);
    return hours ? `${hours}h ${String(minutes % 60).padStart(2, "0")}m` : `${minutes}m`;
};

export const dateLabel = (iso: string, granularity: "day" | "week" | "month"): string => {
    const date = new Date(`${iso}T00:00:00Z`);
    if (granularity === "month") return date.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};
