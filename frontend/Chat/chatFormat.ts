import humanizeDuration from "humanize-duration";
import type { User } from "../Common/UserTypes";

export const ago = (iso: string | null | undefined, now: Date = new Date()): string => {
    if (!iso) return "";
    const elapsed = now.getTime() - new Date(iso).getTime();
    if (elapsed < 60_000) return "just now";
    return `${humanizeDuration(elapsed, { round: true, units: ["y", "mo", "w", "d", "h", "m"], largest: 1 })} ago`;
};

export const displayName = (userId: string | null | undefined, users: Record<string, User>): string => {
    if (!userId) return "Someone";
    const user = users[userId];
    return user ? user.full_name || user.username : "Unknown user";
};

const TABLE_RULE = /^\s*\|?\s*:?-{3,}/;

export const preview = (text: string, length = 240): string => {
    const plain = text
        .split("\n")
        .filter((line) => !TABLE_RULE.test(line))
        .map((line) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").replace(/\s*\|\s*/g, " · "))
        .join(" ")
        .replace(/[#*`>]+/g, "")
        .replace(/(^|\s)_+|_+(?=\s|$)/g, "$1")
        .replace(/\s+/g, " ")
        .trim();
    return plain.length > length ? `${plain.slice(0, length).trimEnd()}…` : plain;
};

export const percent = (used: number, total: number): number =>
    total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
