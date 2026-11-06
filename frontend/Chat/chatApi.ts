import { fetchJson } from "../Common/ApiUtils";
import type { EntityType } from "./types";

export const chatBase = (entityType: EntityType, entityId: string) => `/api/v1/chat/${entityType}/${entityId}`;

export const postJson = <T>(url: string, body?: unknown, method = "POST"): Promise<T> =>
    fetchJson<T>(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
