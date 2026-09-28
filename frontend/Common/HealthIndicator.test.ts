import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/svelte";
import HealthIndicator from "./HealthIndicator.svelte";

const JIRA_DOWN = {
    name: "jira_api",
    severity: "important",
    status: "unhealthy",
};

const SCYLLA_DOWN = {
    name: "scylla",
    severity: "critical",
    status: "unhealthy",
};

const answerWith = (response: object) => {
    const fetchMock = vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ status: "ok", response }),
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

const indicator = (container: HTMLElement) => container.querySelector("[data-health-indicator]");

describe("HealthIndicator", () => {
    it("reads the health summary route", async () => {
        const fetchMock = answerWith({ enabled: true, status: "healthy", failing: [] });
        render(HealthIndicator);

        await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/health/summary"));
    });

    it("shows no icon while every dependency is healthy", async () => {
        const fetchMock = answerWith({ enabled: true, status: "healthy", failing: [] });
        const { container } = render(HealthIndicator);

        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        expect(indicator(container)).toBeNull();
    });

    it("shows no icon while health checking is disabled", async () => {
        const fetchMock = answerWith({ enabled: false, status: "unknown", failing: [] });
        const { container } = render(HealthIndicator);

        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        expect(indicator(container)).toBeNull();
    });

    it.each([
        ["unhealthy", [SCYLLA_DOWN], "text-danger"],
        ["degraded", [JIRA_DOWN], "text-warning"],
        ["unknown", [], "text-secondary"],
    ])("colors the %s icon", async (status, failing, colorClass) => {
        answerWith({ enabled: true, status, failing });
        const { container } = render(HealthIndicator);

        await waitFor(() => expect(indicator(container)).not.toBeNull());
        expect(indicator(container)?.querySelector("i")?.classList.contains(colorClass)).toBe(true);
    });

    it("names the failing dependencies and their status", async () => {
        answerWith({ enabled: true, status: "unhealthy", failing: [SCYLLA_DOWN, JIRA_DOWN] });
        const { container } = render(HealthIndicator);

        await waitFor(() => expect(indicator(container)).not.toBeNull());
        const element = indicator(container) as HTMLElement;
        expect(element.getAttribute("aria-label")).toBe("Argus dependencies unhealthy: scylla, jira_api");
        expect(element.getAttribute("title")).toBe("scylla: unhealthy\njira_api: unhealthy");
    });

    it("says the health process does not answer when the status is unknown", async () => {
        answerWith({ enabled: true, status: "unknown", failing: [] });
        const { container } = render(HealthIndicator);

        await waitFor(() => expect(indicator(container)).not.toBeNull());
        expect(indicator(container)?.getAttribute("aria-label")).toBe("Argus health status unknown");
    });
});
