import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import TestMetadata from "./TestMetadata.svelte";

afterEach(cleanup);

const FULL_METADATA = {
    description: "Basic longevity test running cassandra-stress.",
    tier: "tier1",
    test_type: "longevity",
    duration_class: "short",
    supported_backends: '["aws", "gce", "azure"]',
};

const badgeTexts = (container: HTMLElement) =>
    Array.from(container.querySelectorAll(".badge")).map((node) => node.textContent?.trim());

describe("TestMetadata", () => {
    it("renders a badge for every label", () => {
        const { container } = render(TestMetadata, { metadata: FULL_METADATA });

        expect(badgeTexts(container)).toEqual(["tier1", "longevity", "short", "aws", "gce", "azure"]);
    });

    it("renders the description", () => {
        const { container } = render(TestMetadata, { metadata: FULL_METADATA });

        expect(container.textContent).toContain("Basic longevity test running cassandra-stress.");
    });

    it("splits the supported backends into one badge each", () => {
        const { container } = render(TestMetadata, {
            metadata: { supported_backends: '["aws", "gce"]' },
        });

        expect(badgeTexts(container)).toEqual(["aws", "gce"]);
    });

    it("falls back to the raw value when the backend list is not valid JSON", () => {
        const { container } = render(TestMetadata, {
            metadata: { supported_backends: "['aws', 'gce'" },
        });

        expect(badgeTexts(container)).toEqual(["['aws', 'gce'"]);
    });

    it("renders a key it has never seen, with its name", () => {
        const { container } = render(TestMetadata, { metadata: { owner_team: "sct" } });

        expect(badgeTexts(container)).toEqual(["owner_team: sct"]);
    });

    it("puts the known labels before the unknown ones", () => {
        const { container } = render(TestMetadata, {
            metadata: { owner_team: "sct", tier: "tier1" },
        });

        expect(badgeTexts(container)).toEqual(["tier1", "owner_team: sct"]);
    });

    it("renders nothing for an empty map", () => {
        const { container } = render(TestMetadata, { metadata: {} });

        expect(container.textContent?.trim()).toBe("");
    });

    it("omits the description in compact mode", () => {
        const { container } = render(TestMetadata, { metadata: FULL_METADATA, compact: true });

        expect(container.textContent).not.toContain("Basic longevity test");
        expect(badgeTexts(container)).toContain("tier1");
    });

    it("skips a label whose value is empty", () => {
        const { container } = render(TestMetadata, { metadata: { tier: "", test_type: "longevity" } });

        expect(badgeTexts(container)).toEqual(["longevity"]);
    });
});
