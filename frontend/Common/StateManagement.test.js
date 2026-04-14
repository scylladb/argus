import { describe, it, expect } from "vitest";
import { Base64 } from "js-base64";
import { stateEncoder, stateDecoder } from "./StateManagement.js";

describe("stateEncoder", () => {
    it("returns a URL-safe Base64 string", () => {
        const input = { releases: ["r1", "r2"], filter: true };
        const encoded = stateEncoder(input);
        // Should not contain +, /, or = (URL-safe mode)
        expect(encoded).not.toMatch(/[+/=]/);
    });

    it("encodes data that can be decoded back to the original", () => {
        const input = { key: "value", nested: [1, 2, 3] };
        const encoded = stateEncoder(input);
        const decoded = JSON.parse(Base64.decode(encoded));
        expect(decoded).toEqual(input);
    });

    it("handles empty objects", () => {
        const encoded = stateEncoder({});
        const decoded = JSON.parse(Base64.decode(encoded));
        expect(decoded).toEqual({});
    });

    it("handles arrays as top-level state", () => {
        const input = ["a", "b", "c"];
        const encoded = stateEncoder(input);
        const decoded = JSON.parse(Base64.decode(encoded));
        expect(decoded).toEqual(input);
    });
});

describe("stateDecoder", () => {
    it("decodes state from document.location.search", () => {
        const input = { releases: ["r1"], filter: true };
        const encoded = Base64.encode(JSON.stringify(input), true);
        // Use jsdom's navigation to set the URL search params
        window.history.pushState({}, "", `?state=${encoded}`);

        const result = stateDecoder();
        expect(result).toEqual(input);
    });

    it("returns empty array when no state param is present", () => {
        window.history.pushState({}, "", "?");

        const result = stateDecoder();
        expect(result).toEqual([]);
    });
});
