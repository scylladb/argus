import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import { sendMessage } from "../Stores/AlertStore";
import ReleaseEditor from "./ReleaseEditor.svelte";

const RELEASE = {
    id: "r1", name: "scylla-master", pretty_name: null, description: null, valid_version_regex: null,
    enabled: true, perpetual: false, dormant: false, priority: null,
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const renderEditor = () => {
    const onReleaseEdit = vi.fn();
    render(ReleaseEditor, { props: { releaseData: { ...RELEASE } }, events: { releaseEdit: onReleaseEdit } });
    return onReleaseEdit;
};

describe("ReleaseEditor", () => {
    it.each(["1.5", "-1"])("refuses a priority of %s", async (priority) => {
        const onReleaseEdit = renderEditor();

        await fireEvent.input(screen.getByLabelText("Priority (higher is listed first)"), { target: { value: priority } });
        await fireEvent.click(screen.getByRole("button", { name: "Update" }));

        expect(onReleaseEdit).not.toHaveBeenCalled();
        expect(sendMessage).toHaveBeenCalledWith("error", expect.stringContaining("whole number"), expect.any(String));
    });

    it("saves a whole-number priority", async () => {
        const onReleaseEdit = renderEditor();

        await fireEvent.input(screen.getByLabelText("Priority (higher is listed first)"), { target: { value: "7" } });
        await fireEvent.click(screen.getByRole("button", { name: "Update" }));

        expect(onReleaseEdit).toHaveBeenCalledTimes(1);
        expect(onReleaseEdit.mock.calls[0][0].detail.priority).toBe(7);
    });
});
