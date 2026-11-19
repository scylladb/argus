import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/svelte";

vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import SctEvents from "./SctEvents.svelte";
import type { SCTEvent } from "./SctEvents.svelte";
import type { SCTTestRun } from "../TestRun.svelte";

const RUN_ID = "run-1";

function makeEvent(eventId: string, severity: string, ts: string, message: string, summary: string | null): SCTEvent {
    return {
        run_id: RUN_ID,
        severity,
        ts,
        event_id: eventId,
        duplicate_id: "",
        event_type: "DatabaseLogEvent",
        message,
        summary,
    };
}

const SUMMARIZED_ERROR = makeEvent("error-1", "ERROR", "2026-11-19T12:00:00Z", "error original text", "error summary text");
const EARLIER_WARNING = makeEvent("warning-1", "WARNING", "2026-11-19T11:00:00Z", "warning original text", null);

const EVENTS_BY_SEVERITY: Record<string, SCTEvent[]> = {
    ERROR: [SUMMARIZED_ERROR],
    WARNING: [EARLIER_WARNING],
};

function mockFetch() {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        let response: unknown = [];
        if (url.startsWith("/api/v1/user/preferences")) {
            response = { event_summaries: true };
        } else if (url.includes("/count")) {
            response = 1;
        } else {
            const match = url.match(/\/events\/(\w+)\/get/);
            if (match) response = EVENTS_BY_SEVERITY[match[1]] ?? [];
        }
        return { json: async () => ({ status: "ok", response }) } as Response;
    });
}

function card(eventId: string): HTMLElement | null {
    return document.querySelector(`.sct-event-${eventId}`);
}

function cardBody(eventId: string): string {
    return card(eventId)?.querySelector("pre")?.textContent ?? "";
}

afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
});

describe("SctEvents", () => {
    it("keeps a card's view on its event when an earlier event is inserted", async () => {
        mockFetch();
        render(SctEvents, {
            props: {
                testRun: { id: RUN_ID, test_id: "test-1", status: "passed", end_time: "" } as unknown as SCTTestRun,
                nemeses: [],
                issueAttach: vi.fn(),
            },
        });

        await waitFor(() => expect(cardBody("error-1")).toContain("error summary text"));
        const showOriginal = Array.from(card("error-1")!.querySelectorAll("button"))
            .find((button) => button.textContent?.trim() === "Show original")!;
        await fireEvent.click(showOriginal);
        expect(cardBody("error-1")).toContain("error original text");

        await fireEvent.click(screen.getByRole("button", { name: /WARNING/ }));
        await waitFor(() => expect(card("warning-1")).not.toBeNull());

        expect(cardBody("error-1")).toContain("error original text");
        expect(cardBody("warning-1")).toContain("warning original text");
    });
});
