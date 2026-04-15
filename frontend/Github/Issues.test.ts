import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";

// AlertStore and child-component stores must be mocked before the component
// is imported so Svelte's module evaluation picks up the stubs.
vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Stores/UserlistSubscriber.js", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({});
            return () => {};
        },
    },
}));

import Issues from "./Issues.svelte";

// ---------------------------------------------------------------------------
// Module-level fixtures
// ---------------------------------------------------------------------------

// A minimal successful API response with no issues — enough to reach the
// empty-state branch without rendering child GithubIssue / JiraIssue components.
const EMPTY_OK_RESPONSE = { json: () => Promise.resolve({ status: "ok", response: [] }) };

const BASE_PROPS = {
    runId: "run-1",
    testId: "test-1",
    pluginName: "scylla-cluster-tests",
    id: "run-1",
    submitDisabled: true, // hides the issue-submission form; keeps render minimal
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderIssues(extraProps: Record<string, unknown> = {}) {
    return render(Issues, { props: { ...BASE_PROPS, ...extraProps } });
}

// Pull the URL string that fetch was called with out of the spy.
function capturedUrl(fetchSpy: ReturnType<typeof vi.fn>, callIndex = 0): string {
    return fetchSpy.mock.calls[callIndex][0] as string;
}

// Wait until the component has settled after a fetch: the empty-state text is
// visible, meaning fetching=false and issues=[] have been written back to $state.
// After this point, any spurious $effect re-run would have already fired.
async function waitForFetchToSettle(emptyStateText = "No issues found.") {
    await waitFor(() => expect(screen.getByText(emptyStateText)).toBeTruthy());
    // Flush any remaining microtasks / Svelte scheduler ticks.
    await tick();
    await tick();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Issues.svelte — productVersion filtering", () => {
    let fetchSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        fetchSpy = vi.fn().mockResolvedValue(EMPTY_OK_RESPONSE);
        vi.stubGlobal("fetch", fetchSpy);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        cleanup();
    });

    // --- no spurious re-fetch after mount -----------------------------------

    // NOTE: This test attempts to catch the $effect re-run bug where calling
    // fetchIssues() without untrack() causes the effect to re-run after
    // issues/fetching $state is written back. In jsdom the Svelte scheduler
    // coalesces microtasks fast enough that the spurious call may not be
    // observable within waitFor's timeout, so this test is a best-effort
    // guard rather than a guaranteed regression detector for that specific bug.
    it("fetches exactly once on mount and does not re-fetch after state settles", async () => {
        renderIssues({ productVersion: "6.2.0" });
        await waitForFetchToSettle("No issues linked for version 6.2.0.");
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    // --- query-string construction ------------------------------------------

    it("omits productVersion and includeNoVersion from the request when productVersion is not set", async () => {
        renderIssues();
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        const url = capturedUrl(fetchSpy);
        expect(url).not.toContain("productVersion");
        expect(url).not.toContain("includeNoVersion");
    });

    it("includes productVersion in the request when the prop is provided", async () => {
        renderIssues({ productVersion: "6.2.0" });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        expect(capturedUrl(fetchSpy)).toContain("productVersion=6.2.0");
    });

    it.each([
        {
            productVersion: "6.2.0",
            includeNoVersion: false,
            shouldInclude: false,
            label: "omits includeNoVersion when false",
        },
        {
            productVersion: "6.2.0",
            includeNoVersion: true,
            shouldInclude: true,
            label: "includes includeNoVersion=1 when true",
        },
    ])("$label", async ({ productVersion, includeNoVersion, shouldInclude }) => {
        renderIssues({ productVersion, includeNoVersion });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        const url = capturedUrl(fetchSpy);
        if (shouldInclude) {
            expect(url).toContain("includeNoVersion=1");
        } else {
            expect(url).not.toContain("includeNoVersion");
        }
    });

    it("omits includeNoVersion even when true if productVersion is not set", async () => {
        renderIssues({ includeNoVersion: true });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        expect(capturedUrl(fetchSpy)).not.toContain("includeNoVersion");
    });

    // --- reactive re-fetch --------------------------------------------------

    it("re-fetches when productVersion prop changes", async () => {
        const { rerender } = renderIssues({ productVersion: "6.1.0" });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        await rerender({ props: { ...BASE_PROPS, productVersion: "6.2.0" } });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

        expect(capturedUrl(fetchSpy, 1)).toContain("productVersion=6.2.0");
    });

    it("re-fetches when includeNoVersion prop changes", async () => {
        const { rerender } = renderIssues({ productVersion: "6.2.0", includeNoVersion: false });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        await rerender({ props: { ...BASE_PROPS, productVersion: "6.2.0", includeNoVersion: true } });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

        expect(capturedUrl(fetchSpy, 1)).toContain("includeNoVersion=1");
    });

    // --- empty-state messages -----------------------------------------------
    it.each([
        {
            productVersion: "6.2.0",
            expected: "No issues linked for version 6.2.0.",
            label: "named version",
        },
        {
            productVersion: "!noVersion",
            expected: "No issues linked for version runs without a version.",
            label: "!noVersion sentinel",
        },
    ])("shows version-specific empty-state for $label", async ({ productVersion, expected }) => {
        renderIssues({ productVersion });
        await waitFor(() => expect(screen.getByText(expected)).toBeTruthy());
    });

    it("shows generic empty-state when productVersion is not set", async () => {
        renderIssues();
        await waitFor(() => expect(screen.getByText("No issues found.")).toBeTruthy());
    });
});
