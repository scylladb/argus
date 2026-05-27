import { sendMessage } from "../Stores/AlertStore";

export interface ApiResponse<T = unknown> {
    status: string;
    response: T;
    message?: string;
}

/**
 * Fetch a JSON endpoint that returns the standard Argus {status, response} envelope.
 * Throws on non-OK HTTP status or when the API returns status !== "ok".
 */
export const fetchJson = async <T = unknown>(url: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(url, init);
    const data: ApiResponse<T> | null = await response.json().catch(() => null);
    if (!data) {
        throw new Error(`HTTP ${response.status} on ${url}`);
    }
    if (data.status !== "ok") {
        const message =
            (data as any).message ??
            (data.response as any)?.arguments?.[0] ??
            (data.response as any)?.message ??
            `HTTP ${response.status}`;
        throw new Error(message);
    }
    return data.response;
};

/**
 * Truncate a string, keeping `head` chars from the start and `tail` chars from the end,
 * joined by an ellipsis. Returns "—" for empty/null values.
 */
export const truncate = (value: string | null | undefined, head = 14, tail = 8): string => {
    if (!value) return "—";
    const trimmed = String(value).trim();
    if (trimmed.length <= head + tail + 1) return trimmed;
    return `${trimmed.slice(0, head)}…${trimmed.slice(-tail)}`;
};

export interface KnownHostSummary {
    type: string;
    short: string;
}

/**
 * Parse a known_hosts line (e.g. "hostname keytype base64key") and return a short summary.
 */
export const knownHostSummary = (entry: string | null | undefined): KnownHostSummary => {
    if (!entry) return { type: "—", short: "—" };
    const parts = String(entry).trim().split(/\s+/);
    if (parts.length < 3) return { type: "?", short: truncate(entry) };
    return { type: parts[1], short: truncate(parts[2], 10, 6) };
};

/**
 * Copy a value to the clipboard and send a success/error alert.
 */
export const copyToClipboard = async (value: string, label: string, context = "copyToClipboard"): Promise<void> => {
    try {
        await navigator.clipboard.writeText(value);
        sendMessage("success", `${label} copied to clipboard.`, context);
    } catch (error: any) {
        console.error(context, error);
        sendMessage("error", `Could not copy ${label.toLowerCase()}: ${error.message}`, context);
    }
};
