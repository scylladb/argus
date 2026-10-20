import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/svelte";

vi.mock("svelte/transition", () => ({ slide: () => ({ duration: 0 }) }));

import NemesisList from "./NemesisList.svelte";
import type { NemesisInfo, NemesisResource } from "./types";

const T0 = Date.UTC(2026, 9, 20, 10, 0, 0) / 1000;

const nemesis = (overrides: Partial<NemesisInfo> = {}): NemesisInfo => ({
    class_name: "DisruptRestartNodeMonkey",
    name: "disrupt_restart_node",
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

const rowNames = () => screen.getAllByRole("rowgroup").map((group) => within(group).getAllByRole("button")[0].textContent?.trim());

const filter = async (value: string) => fireEvent.input(screen.getByLabelText("Filter"), { target: { value } });

afterEach(() => cleanup());

describe("NemesisList", () => {
    it("renders a row per nemesis with name, node, status and times", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(screen.getAllByRole("rowgroup")).toHaveLength(3);
        expect(screen.getAllByText("db-node-1")).toHaveLength(3);
        expect(screen.getAllByText("Succeeded", { selector: ".badge" })).toHaveLength(2);
        expect(screen.getByText("Failed", { selector: ".badge" })).toBeTruthy();
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

        expect(screen.getAllByRole("rowgroup")).toHaveLength(1);
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
        expect(screen.getByText("DisruptRestartNodeMonkey")).toBeTruthy();
        expect(screen.getByText("10.0.0.5")).toBeTruthy();
        expect(screen.getByText("running")).toBeTruthy();
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

        expect(screen.getAllByRole("rowgroup")).toHaveLength(2);
        await fireEvent.click(screen.getByRole("button", { name: "ModifyTableMonkey" }));

        expect(screen.getByText("ModifyTable")).toBeTruthy();
        expect(screen.queryByText("GrowShrink")).toBeNull();
        expect(screen.getByRole("button", { name: "GrowShrinkClusterNemesis" }).getAttribute("aria-expanded")).toBe("false");
    });

    it("collapses the details on a second click", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const toggle = screen.getByRole("button", { name: "disrupt_restart_node" });

        await fireEvent.click(toggle);
        await fireEvent.click(toggle);

        expect(toggle.getAttribute("aria-expanded")).toBe("false");
        expect(screen.queryByText("DisruptRestartNodeMonkey")).toBeNull();
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
        const highlighted = () => screen.getAllByRole("rowgroup").filter((group) => group.classList.contains("bg-primary-subtle"));

        await fireEvent.mouseEnter(screen.getAllByTitle("db-node-1")[0]);
        expect(highlighted().map((group) => within(group).getAllByRole("button")[0].textContent?.trim())).toEqual(["c", "a"]);

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

    it("filters by status from the dropdown", async () => {
        render(NemesisList, { props: { nemeses: three(), resources } });
        const select = screen.getByLabelText("Status") as HTMLSelectElement;

        expect([...select.options].map((option) => option.textContent)).toEqual(["All statuses", "Failed", "Succeeded"]);

        await fireEvent.change(select, { target: { value: "failed" } });
        expect(rowNames()).toEqual(["disrupt_stop_node"]);
        expect(screen.getByText("1 of 3 match")).toBeTruthy();

        await fireEvent.change(select, { target: { value: "" } });
        expect(rowNames()).toHaveLength(3);
    });

    it("labels the filter input", () => {
        render(NemesisList, { props: { nemeses: three(), resources } });

        expect(screen.getByLabelText("Filter").tagName).toBe("INPUT");
    });
});
