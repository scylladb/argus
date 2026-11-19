import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import ReleaseManagerGroup from "./ReleaseManagerGroup.svelte";

afterEach(cleanup);

const GROUP = { id: "g-1", name: "longevity", pretty_name: "Longevity", build_system_id: "", enabled: true };

describe("ReleaseManagerGroup", () => {
    it("selects the group from its name button", async () => {
        const onselect = vi.fn();
        render(ReleaseManagerGroup, { group: { ...GROUP }, groups: [GROUP], onselect });

        await fireEvent.click(screen.getByRole("button", { name: /longevity/ }));

        expect(onselect).toHaveBeenCalledOnce();
    });

    it("marks the name button of the selected group as current", () => {
        render(ReleaseManagerGroup, { group: { ...GROUP }, groups: [GROUP], selected: true });

        expect(screen.getByRole("button", { name: /longevity/ }).getAttribute("aria-current")).toBe("true");
    });

    it("leaves the name button of another group without aria-current", () => {
        render(ReleaseManagerGroup, { group: { ...GROUP }, groups: [GROUP] });

        expect(screen.getByRole("button", { name: /longevity/ }).hasAttribute("aria-current")).toBe(false);
    });

    it("does not select the group from its edit and delete buttons", async () => {
        const onselect = vi.fn();
        render(ReleaseManagerGroup, { group: { ...GROUP }, groups: [GROUP], onselect });

        await fireEvent.click(screen.getByTitle("Edit"));
        await fireEvent.click(screen.getByTitle("Delete"));

        expect(onselect).not.toHaveBeenCalled();
    });
});
