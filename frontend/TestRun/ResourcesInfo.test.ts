import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";
import ResourcesInfo from "./ResourcesInfo.svelte";

const resource = (name: string) => ({
    name,
    state: "running",
    resource_type: "db_node",
    instance_info: {
        provider: "aws",
        region: "eu-west-1",
        public_ip: "1.2.3.4",
        private_ip: "10.0.0.5",
        dc_name: "eu-west",
        rack_name: "1a",
        creation_time: 1_700_000_000,
        termination_time: 0,
        termination_reason: "",
        shards_amount: 8,
        instance_type: "i4i.large",
    },
});

const props = { backend: "aws", run_id: "run-1", regions: ["eu-west-1"] };

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe("ResourcesInfo", () => {
    it("highlights and scrolls to the focused resource", () => {
        render(ResourcesInfo, { props: { ...props, resources: [resource("db-node-1"), resource("db-node-2")], focusResource: "db-node-2" } });

        const row = screen.getByText("db-node-2").closest("tr");
        expect(row?.classList.contains("table-primary")).toBe(true);
        expect(screen.getByText("db-node-1").closest("tr")?.classList.contains("table-primary")).toBe(false);
        expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    });

    it("highlights nothing without a focused resource", () => {
        render(ResourcesInfo, { props: { ...props, resources: [resource("db-node-1")] } });

        expect(screen.getByText("db-node-1").closest("tr")?.classList.contains("table-primary")).toBe(false);
        expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    });
});
