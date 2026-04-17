import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiMethodCall } from "./ApiUtils.js";

// Mock the AlertStore so sendMessage calls don't hit real store logic.
// This pattern works for any module that produces side effects you want to
// observe or suppress in tests.
vi.mock("../Stores/AlertStore", () => ({
    sendMessage: vi.fn(),
}));

// Re-import after mock registration so we can assert on calls.
import { sendMessage } from "../Stores/AlertStore";

describe("apiMethodCall", () => {
    let fetchSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        // Stub the global fetch so no real HTTP requests are made.
        // Each test configures its own mockResolvedValueOnce / mockRejectedValueOnce.
        fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);
        vi.mocked(sendMessage).mockClear();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("returns the parsed response on success", async () => {
        const payload = { status: "ok", response: { items: [1, 2, 3] } };
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve(payload),
        });

        const result = await apiMethodCall("/api/v1/example", { q: "test" });

        expect(fetchSpy).toHaveBeenCalledWith("/api/v1/example", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ q: "test" }),
        });
        expect(result).toEqual(payload);
    });

    it("uses the specified HTTP method", async () => {
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve({ status: "ok", response: {} }),
        });

        await apiMethodCall("/api/v1/thing", null, "GET");

        expect(fetchSpy).toHaveBeenCalledWith("/api/v1/thing", expect.objectContaining({ method: "GET" }));
    });

    it("sends an error alert when API returns status error", async () => {
        const errorPayload = {
            status: "error",
            response: { arguments: ["Something went wrong"] },
        };
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve(errorPayload),
        });

        const result = await apiMethodCall("/api/v1/fail", {});

        // apiMethodCall returns undefined on error path
        expect(result).toBeUndefined();
        expect(sendMessage).toHaveBeenCalledWith("error", "API Error.\nMessage: Something went wrong", "apiMethodCall");
    });

    it("sends a generic error alert on network failure", async () => {
        fetchSpy.mockRejectedValueOnce(new TypeError("Failed to fetch"));

        const result = await apiMethodCall("/api/v1/down", {});

        expect(result).toBeUndefined();
        expect(sendMessage).toHaveBeenCalledWith(
            "error",
            "Unhandled API Error occured. \nCheck console for details.",
            "apiMethodCall",
        );
    });

    it("returns undefined when response JSON is not status ok", async () => {
        // A non-error, non-ok status (e.g. missing status field)
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve({ status: "unknown" }),
        });

        const result = await apiMethodCall("/api/v1/weird", {});
        expect(result).toBeUndefined();
    });
});
