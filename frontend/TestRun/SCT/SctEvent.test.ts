import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import SctEvent from "./SctEvent.svelte";
import type { SCTEvent } from "./SctEvents.svelte";
import type { SCTTestRun } from "../TestRun.svelte";

const MESSAGE = "(DatabaseLogEvent Severity.ERROR) period_type=one-time event_id=abc: original event text";
const SUMMARY = "DatabaseLogEvent ERROR | node-1\nerror: summarized text";

function makeEvent(summary: string | null): SCTEvent {
    return {
        run_id: "run-1",
        severity: "ERROR",
        ts: "2026-11-19T10:00:00Z",
        event_id: "event-1",
        duplicate_id: "",
        event_type: "DatabaseLogEvent",
        message: MESSAGE,
        summary,
    };
}

function renderEvent(showSummaries: boolean, summary: string | null = SUMMARY) {
    return render(SctEvent, {
        props: {
            event: makeEvent(summary),
            run: { id: "run-1", test_id: "test-1" } as SCTTestRun,
            issues: [],
            focusDuplicate: vi.fn(),
            filterState: {},
            options: {},
            issueAttach: vi.fn(),
            refreshIssues: vi.fn(),
            filterString: "",
            duplicateIdShowTable: {},
            showSummaries,
        },
    });
}

function eventBody(): string {
    return document.querySelector("pre")?.textContent ?? "";
}

afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
});

describe("SctEvent summary view", () => {
    it("starts on the original message when summaries are off, and offers the summary", async () => {
        renderEvent(false);
        expect(eventBody()).toContain("original event text");
        expect(screen.queryByText("AI summary")).toBeNull();

        await fireEvent.click(screen.getByRole("button", { name: "Show summary" }));
        expect(eventBody()).toContain("summarized text");
        expect(screen.getByText("AI summary")).toBeTruthy();
    });

    it("renders unchanged when summaries are off and the event has no summary", () => {
        renderEvent(false, null);
        expect(eventBody()).toContain("original event text");
        expect(screen.queryByRole("button", { name: "Show summary" })).toBeNull();
    });

    it("shows the summary with a badge when summaries are on, and toggles to the original", async () => {
        renderEvent(true);
        expect(eventBody()).toContain("summarized text");
        expect(eventBody()).not.toContain("original event text");
        expect(screen.getByText("AI summary")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Show original" }));
        expect(eventBody()).toContain("original event text");
        expect(screen.queryByText("AI summary")).toBeNull();

        await fireEvent.click(screen.getByRole("button", { name: "Show summary" }));
        expect(eventBody()).toContain("summarized text");
    });

    it("expands a long original message when switching from the summary", async () => {
        const longTail = "x".repeat(700) + " end of the long event";
        render(SctEvent, {
            props: {
                event: { ...makeEvent(SUMMARY), message: MESSAGE + longTail },
                run: { id: "run-1", test_id: "test-1" } as SCTTestRun,
                issues: [],
                focusDuplicate: vi.fn(),
                filterState: {},
                options: {},
                issueAttach: vi.fn(),
                refreshIssues: vi.fn(),
                filterString: "",
                duplicateIdShowTable: {},
                showSummaries: true,
            },
        });

        await fireEvent.click(screen.getByRole("button", { name: "Show original" }));
        expect(eventBody()).toContain("end of the long event");
    });

    it("renders unchanged when summaries are on but the event has no summary", () => {
        renderEvent(true, null);
        expect(eventBody()).toContain("original event text");
        expect(screen.queryByText("AI summary")).toBeNull();
        expect(screen.queryByRole("button", { name: "Show summary" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Show original" })).toBeNull();
    });

    it("copies the original message from the summary view", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
        renderEvent(true);

        const copyButton = Array.from(document.querySelectorAll<HTMLButtonElement>("button.btn-success"))
            .find((button) => !button.closest(".btn-group"));
        await fireEvent.click(copyButton!);
        expect(writeText).toHaveBeenCalledWith(MESSAGE);
    });
});
