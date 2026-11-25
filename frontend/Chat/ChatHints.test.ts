import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";

import ChatHints from "./ChatHints.svelte";
import { DOCS_URL, EXAMPLE_GROUPS } from "./chatExamples";

describe("ChatHints", () => {
    afterEach(cleanup);

    it("lists every group of examples with a link to the documentation", () => {
        render(ChatHints, { props: { onpick: vi.fn() } });

        for (const group of EXAMPLE_GROUPS) {
            expect(screen.getByRole("region", { name: group.title })).toBeTruthy();
        }
        expect(screen.getByRole("link", { name: /Everything the chat can do/ }).getAttribute("href")).toBe(DOCS_URL);
    });

    it("hands a clicked example to the caller", async () => {
        const onpick = vi.fn();
        render(ChatHints, { props: { onpick } });

        await fireEvent.click(screen.getByRole("button", { name: "Run the week1 tests of the <plan> plan on gce." }));

        expect(onpick).toHaveBeenCalledWith("Run the week1 tests of the <plan> plan on gce.");
    });
});
