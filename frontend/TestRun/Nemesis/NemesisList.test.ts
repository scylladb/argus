import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";
import { tick } from "svelte";

vi.mock("svelte/transition", () => ({ slide: () => ({ duration: 0 }) }));

vi.hoisted(() => {
    window.matchMedia = (query: string) =>
        ({
            matches: false,
            media: query,
            onchange: null,
            addEventListener: () => {},
            removeEventListener: () => {},
            addListener: () => {},
            removeListener: () => {},
            dispatchEvent: () => false,
        }) as unknown as MediaQueryList;
    Element.prototype.getAnimations = () => [];
});

import NemesisList from "./NemesisList.svelte";
import type { NemesisInfo, NemesisResource } from "./types";

const T0 = Date.UTC(2026, 9, 20, 10, 0, 0) / 1000;

const nemesis = (overrides: Partial<NemesisInfo> = {}): NemesisInfo => ({
    class_name: "DisruptRestartNodeMonkey",
    name: "disrupt_restart_node",
    description_digest: "digest-1",
    description: "Restart (hard) the target node.\n\nWaits for the node to rejoin.",
    duration: 90,
    target_node: { name: "db-node-1", ip: "1.2.3.4", shards: 8 },
    status: "succeeded",
    start_time: T0,
    end_time: T0 + 90,
    stack_trace: "",
    ...overrides,
});

const resources: NemesisResource[] = [{ name: "db-node-1", state: "running", instance_info: { private_ip: "10.0.0.5" } }];

const three = () => [
    nemesis({ name: "disrupt_restart_node", start_time: T0, end_time: T0 + 90 }),
    nemesis({
        name: "disrupt_stop_node", class_name: "DisruptStopNodeMonkey", description: "Stop the node.",
        status: "failed", start_time: T0 + 600, end_time: T0 + 700, stack_trace: "Traceback: boom",
    }),
    nemesis({ name: "disrupt_add_node", class_name: "DisruptAddNodeMonkey", description: null, start_time: T0 + 300, end_time: 0 }),
];

const rows = () => screen.getAllByRole("rowgroup").filter((row) => row.classList.contains("nemesis-row"));

const rowNames = () => rows().map((row) => row.querySelector(".nemesis-name")?.textContent?.trim());

const filter = async (value: string) => fireEvent.input(screen.getByLabelText("Filter"), { target: { value } });

afterEach(() => cleanup());

describe("NemesisList", () => {
    it("renders a row per nemesis with name, node, status and times", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(rows()).toHaveLength(3);
        expect(screen.getAllByText("db-node-1")).toHaveLength(3);
        expect(screen.getAllByText("Succeeded", { selector: ".nemesis-row .badge" })).toHaveLength(2);
        expect(screen.getByText("Failed", { selector: ".nemesis-row .badge" })).toBeTruthy();
        expect(screen.getByText("2026-10-20 10:00:00")).toBeTruthy();
        expect(screen.getByText("2026-10-20 10:01:30")).toBeTruthy();
    });

    it("shows In progress for a nemesis without an end time", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(screen.getByText("In progress")).toBeTruthy();
    });

    it("shows the first line of the description under the name and the full text as the title", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        const subline = screen.getByText("Restart (hard) the target node.");
        expect(subline.getAttribute("title")).toBe("Restart (hard) the target node.\n\nWaits for the node to rejoin.");
    });

    it("renders no subline when the description is null", () => {
        render(NemesisList, { props: { nemeses: [nemesis({ description: null })], resources } });

        expect(rows()).toHaveLength(1);
        expect(screen.queryByText(/Restart/)).toBeNull();
    });

    it("orders by start time, newest first, by default", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(rowNames()).toEqual(["disrupt_stop_node", "disrupt_add_node", "disrupt_restart_node"]);
    });

    it("sorts by name on a header click and reverses on the second click", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await fireEvent.click(screen.getByRole("button", { name: "Nemesis" }));
        expect(rowNames()).toEqual(["disrupt_add_node", "disrupt_restart_node", "disrupt_stop_node"]);
        expect(screen.getByRole("columnheader", { name: /Nemesis/ }).getAttribute("aria-sort")).toBe("ascending");

        await fireEvent.click(screen.getByRole("button", { name: "Nemesis" }));
        expect(rowNames()).toEqual(["disrupt_stop_node", "disrupt_restart_node", "disrupt_add_node"]);
        expect(screen.getByRole("columnheader", { name: /Nemesis/ }).getAttribute("aria-sort")).toBe("descending");
    });

    it("does not inherit the direction when switching column", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await fireEvent.click(screen.getByRole("button", { name: "Started" }));
        expect(screen.getByRole("columnheader", { name: /Started/ }).getAttribute("aria-sort")).toBe("ascending");

        await fireEvent.click(screen.getByRole("button", { name: "Nemesis" }));
        expect(screen.getByRole("columnheader", { name: /Nemesis/ }).getAttribute("aria-sort")).toBe("ascending");
        expect(screen.getByRole("columnheader", { name: /Started/ }).getAttribute("aria-sort")).toBe("none");
    });

    it("filters rows with a regular expression", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await filter("^disrupt_(restart|stop)");

        expect(rowNames()).toEqual(["disrupt_stop_node", "disrupt_restart_node"]);
    });

    it("filters by the description", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await filter("rejoin");

        expect(rowNames()).toEqual(["disrupt_restart_node"]);
    });

    it("falls back to a substring match for an invalid regular expression", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await filter("(hard");

        expect(rowNames()).toEqual(["disrupt_restart_node"]);
    });

    it("shows the count of matching nemeses", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        expect(screen.getByText("3 nemeses")).toBeTruthy();

        await filter("rejoin");

        expect(screen.getByText("1 of 3 match")).toBeTruthy();
    });

    it("shows an empty state without nemeses", () => {
        render(NemesisList, { props: { nemeses: [], resources } });

        expect(screen.getByText("No nemeses were reported for this run.")).toBeTruthy();
        expect(screen.queryByRole("table")).toBeNull();
    });

    it("shows an empty state when nothing matches the filter", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        await filter("nothing like this");

        expect(screen.getByText("No nemesis matches the filter.")).toBeTruthy();
        expect(screen.getByRole("columnheader", { name: /Nemesis/ })).toBeTruthy();
    });

    it("expands the details of a nemesis", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        const toggle = screen.getByRole("button", { name: "disrupt_restart_node" });
        await fireEvent.click(toggle);

        expect(toggle.getAttribute("aria-expanded")).toBe("true");
        expect(screen.getByDisplayValue("DisruptRestartNodeMonkey")).toBeTruthy();
        expect(screen.getByDisplayValue("10.0.0.5")).toBeTruthy();
        expect(screen.getByDisplayValue("running")).toBeTruthy();
    });

    it("expands from a click anywhere on the row except its buttons and times", async () => {
        const onSelectNode = vi.fn();
        render(NemesisList, { props: { nemeses: three(), resources, onSelectNode } });
        const toggle = screen.getByRole("button", { name: "disrupt_restart_node" });
        const row = toggle.closest(".nemesis-row") as HTMLElement;

        await fireEvent.click(within(row).getByText("Restart (hard) the target node."));
        expect(toggle.getAttribute("aria-expanded")).toBe("true");

        await fireEvent.click(within(row).getByRole("button", { name: "db-node-1" }));
        expect(onSelectNode).toHaveBeenCalledWith("db-node-1");
        expect(toggle.getAttribute("aria-expanded")).toBe("true");

        await fireEvent.click(within(row).getByRole("button", { name: "Filter by db-node-1" }));
        expect(within(row).getByRole("button", { name: "Filter by db-node-1" }).getAttribute("aria-pressed")).toBe("true");
        expect(toggle.getAttribute("aria-expanded")).toBe("true");

        await fireEvent.click(within(row).getByText("2026-10-20 10:00:00"));
        expect(toggle.getAttribute("aria-expanded")).toBe("true");

        await fireEvent.click(toggle);
        expect(toggle.getAttribute("aria-expanded")).toBe("false");
    });

    it("toggles with a real button and moves between rows with the keyboard", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const [first, second, third] = rows().map((row) => within(row).getAllByRole("button")[0]);
        expect(first.tagName).toBe("BUTTON");
        expect(first.getAttribute("aria-expanded")).toBe("false");
        expect(within(rows()[0]).getAllByRole("cell")).toHaveLength(5);

        first.focus();
        await fireEvent.keyDown(first, { key: "ArrowDown" });
        expect(document.activeElement).toBe(second);
        await fireEvent.keyDown(second, { key: "End" });
        expect(document.activeElement).toBe(third);
        await fireEvent.keyDown(third, { key: "ArrowDown" });
        expect(document.activeElement).toBe(third);
        await fireEvent.keyDown(third, { key: "ArrowUp" });
        expect(document.activeElement).toBe(second);
        await fireEvent.keyDown(second, { key: "Home" });
        expect(document.activeElement).toBe(first);
    });

    it("narrows the list to one status from the badge and clears it again", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const failed = screen.getByRole("button", { name: "Filter by status Failed" });

        await fireEvent.click(failed);
        expect(rowNames()).toEqual(["disrupt_stop_node"]);
        expect(failed.getAttribute("aria-pressed")).toBe("true");
        expect(screen.getByText("1 of 3 match")).toBeTruthy();

        await fireEvent.click(failed);
        expect(rowNames()).toHaveLength(3);
        expect(failed.getAttribute("aria-pressed")).toBe("false");
    });

    it("keeps the details open when a refreshed collection arrives", async () => {
        const { rerender } = render(NemesisList, { props: { nemeses: three(), resources } });
        await fireEvent.click(screen.getByRole("button", { name: "disrupt_add_node" }));

        const [restart, stop, add] = three();
        await rerender({
            nemeses: [restart, stop, { ...add, status: "failed", end_time: T0 + 400, stack_trace: "Traceback: late" }],
            resources,
        });

        expect(screen.getByRole("button", { name: "disrupt_add_node" }).getAttribute("aria-expanded")).toBe("true");
        expect(screen.getByText("Failure reason")).toBeTruthy();
        expect(screen.getByText("Traceback: late")).toBeTruthy();
    });

    it("renders two nemeses that share a start time and expands them independently", async () => {
        const twins = [
            nemesis({ name: "GrowShrinkClusterNemesis", class_name: "GrowShrink", start_time: T0, description: null }),
            nemesis({ name: "ModifyTableMonkey", class_name: "ModifyTable", start_time: T0, description: null }),
        ];
        render(NemesisList, { props: { nemeses: twins, resources } });

        expect(rows()).toHaveLength(2);
        await fireEvent.click(screen.getByRole("button", { name: "ModifyTableMonkey" }));

        expect(screen.getByDisplayValue("ModifyTable")).toBeTruthy();
        expect(screen.queryByDisplayValue("GrowShrink")).toBeNull();
        expect(screen.getByRole("button", { name: "GrowShrinkClusterNemesis" }).getAttribute("aria-expanded")).toBe("false");
    });

    it("collapses the details on a second click", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const toggle = screen.getByRole("button", { name: "disrupt_restart_node" });

        await fireEvent.click(toggle);
        await fireEvent.click(toggle);

        expect(toggle.getAttribute("aria-expanded")).toBe("false");
        expect(screen.queryByDisplayValue("DisruptRestartNodeMonkey")).toBeNull();
    });

    it("offers the target node as a link into the resources", async () => {
        const onSelectNode = vi.fn();
        render(NemesisList, { props: { nemeses: three(), resources, onSelectNode } });

        await fireEvent.click(screen.getAllByRole("button", { name: "db-node-1" })[0]);

        expect(onSelectNode).toHaveBeenCalledWith("db-node-1");
    });

    it("renders the target node as plain text without a handler", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(screen.queryAllByRole("button", { name: "db-node-1" })).toHaveLength(0);
        expect(screen.getAllByText("db-node-1")).toHaveLength(3);
    });

    it("highlights every row of the hovered node", async () => {
        const nemeses = [
            nemesis({ name: "a", start_time: T0, target_node: { name: "db-node-1", ip: null, shards: null } }),
            nemesis({ name: "b", start_time: T0 + 100, target_node: { name: "db-node-2", ip: null, shards: null } }),
            nemesis({ name: "c", start_time: T0 + 200, target_node: { name: "db-node-1", ip: null, shards: null } }),
        ];
        render(NemesisList, { props: { nemeses, resources } });
        const highlighted = () => rows().filter((row) => row.classList.contains("bg-primary-subtle"));

        await fireEvent.mouseEnter(screen.getAllByTitle("db-node-1")[0]);
        expect(highlighted().map((row) => row.querySelector(".nemesis-name")?.textContent?.trim())).toEqual(["c", "a"]);

        await fireEvent.mouseLeave(screen.getAllByTitle("db-node-1")[0]);
        expect(highlighted()).toHaveLength(0);
    });

    it("narrows the list to one node from the row button and clears it again", async () => {
        const nemeses = [
            nemesis({ name: "a", start_time: T0, target_node: { name: "db-node-1", ip: null, shards: null } }),
            nemesis({ name: "b", start_time: T0 + 100, target_node: { name: "db-node-2", ip: null, shards: null } }),
            nemesis({ name: "c", start_time: T0 + 200, target_node: { name: "db-node-1", ip: null, shards: null } }),
        ];
        render(NemesisList, { props: { nemeses, resources } });

        const nodeFilter = screen.getByRole("button", { name: "Filter by db-node-2" });
        expect(nodeFilter.getAttribute("title")).toBe("Show only db-node-2");

        await fireEvent.click(nodeFilter);
        expect(rowNames()).toEqual(["b"]);
        expect(screen.getByText("1 of 3 match")).toBeTruthy();
        expect(nodeFilter.getAttribute("aria-pressed")).toBe("true");
        expect(nodeFilter.getAttribute("title")).toBe("Show every node");

        await fireEvent.click(screen.getByRole("button", { name: "Clear the node filter" }));
        expect(rowNames()).toEqual(["c", "b", "a"]);

        await fireEvent.click(screen.getAllByRole("button", { name: "Filter by db-node-1" })[0]);
        expect(rowNames()).toEqual(["c", "a"]);
        await fireEvent.click(screen.getAllByRole("button", { name: "Filter by db-node-1" })[0]);
        expect(rowNames()).toEqual(["c", "b", "a"]);
    });

    it("starts with every status selected and filters by deselecting one", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const selected = () => [...document.querySelectorAll("ul.selected li")].map((item) => item.textContent?.trim());

        expect(selected()).toEqual(["Failed", "Succeeded"]);
        expect(screen.getByText("3 nemeses")).toBeTruthy();

        await fireEvent.mouseUp(screen.getByTitle("Remove Failed"));
        await fireEvent.click(screen.getByTitle("Remove Failed"));
        expect(rowNames()).toEqual(["disrupt_add_node", "disrupt_restart_node"]);
        expect(screen.getByText("2 of 3 match")).toBeTruthy();

        const input = screen.getByLabelText("Status");
        await fireEvent.focus(input);
        const option = screen.getByText("Failed", { selector: "ul.options *" });
        await fireEvent.mouseUp(option);
        await fireEvent.click(option);
        expect(rowNames()).toHaveLength(3);
        expect(screen.getByText("3 nemeses")).toBeTruthy();
    });

    it("resets to every status when the last one is deselected or all are removed", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const selected = () => [...document.querySelectorAll("ul.selected li")].map((item) => item.textContent?.trim());
        const remove = async (label: string) => {
            await fireEvent.mouseUp(screen.getByTitle(`Remove ${label}`));
            await fireEvent.click(screen.getByTitle(`Remove ${label}`));
            await tick();
            await tick();
        };

        await remove("Failed");
        await remove("Succeeded");
        expect(selected()).toEqual(["Failed", "Succeeded"]);
        expect(rowNames()).toHaveLength(3);
        expect(screen.getByText("3 nemeses")).toBeTruthy();

        await fireEvent.mouseUp(screen.getByTitle("Reset to every status"));
        await fireEvent.click(screen.getByTitle("Reset to every status"));
        await tick();
        await tick();
        expect(selected()).toEqual(["Failed", "Succeeded"]);
        expect(rowNames()).toHaveLength(3);
    });

    it("shows the first page and loads more from the bottom", async () => {
        const many = Array.from({ length: 250 }, (_, index) => nemesis({ name: `nemesis_${index}`, start_time: T0 + index }));
        render(NemesisList, { props: { nemeses: many, resources } });

        expect(rows()).toHaveLength(100);
        expect(screen.getByText("Showing 100 of 250")).toBeTruthy();
        expect(screen.getByText("250 nemeses")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Load 100 more" }));
        expect(rows()).toHaveLength(200);

        await fireEvent.click(screen.getByRole("button", { name: "Load 50 more" }));
        expect(rows()).toHaveLength(250);
        expect(screen.queryByText(/Showing/)).toBeNull();
    });

    it("changes the page size and starts over when a filter changes", async () => {
        const many = Array.from({ length: 250 }, (_, index) => nemesis({ name: `nemesis_${index}`, start_time: T0 + index }));
        render(NemesisList, { props: { nemeses: many, resources } });

        await fireEvent.change(screen.getByLabelText("Show"), { target: { value: "50" } });
        expect(rows()).toHaveLength(50);
        expect(screen.getByText("Showing 50 of 250")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Load 50 more" }));
        expect(rows()).toHaveLength(100);

        await filter("nemesis_1");
        expect(screen.getByText("Showing 50 of 111")).toBeTruthy();
        expect(rows()).toHaveLength(50);
    });

    it("keeps a status selection when an excluded status disappears on a refresh", async () => {
        const { rerender } = render(NemesisList, { props: { nemeses: three(), resources } });
        await fireEvent.mouseUp(screen.getByTitle("Remove Failed"));
        await fireEvent.click(screen.getByTitle("Remove Failed"));
        await tick();

        const [restart, , add] = three();
        await rerender({ nemeses: [restart, { ...add, status: "running", end_time: 0 }], resources });
        await tick();
        expect(rowNames()).toEqual(["disrupt_add_node", "disrupt_restart_node"]);

        await fireEvent.mouseUp(screen.getByTitle("Remove Running"));
        await fireEvent.click(screen.getByTitle("Remove Running"));
        await tick();
        await tick();
        expect(rowNames()).toEqual(["disrupt_restart_node"]);
        expect(screen.getByText("1 of 2 match")).toBeTruthy();
    });

    it("labels the filter input", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(screen.getByLabelText("Filter").tagName).toBe("INPUT");
    });
});
