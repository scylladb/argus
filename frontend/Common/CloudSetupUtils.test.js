import { describe, it, expect } from "vitest";
import {
    clusterTypeLabel,
    networkTypeLabel,
    isCloudManagedDbCluster,
    getDbNodeSetup,
} from "./CloudSetupUtils.js";

const resource = (name, resource_type, instance_type) => ({
    name,
    resource_type,
    instance_info: { instance_type },
});

describe("labels", () => {
    it("maps known values and passes unknown ones through", () => {
        expect(clusterTypeLabel("xcloud")).toBe("XCloud");
        expect(clusterTypeLabel("standard")).toBe("Standard");
        expect(clusterTypeLabel("sandbox")).toBe("sandbox");
        expect(clusterTypeLabel(null)).toBeNull();
        expect(networkTypeLabel("private-vpc")).toBe("Private (VPC peering)");
        expect(networkTypeLabel("public")).toBe("Public");
        expect(networkTypeLabel(undefined)).toBeNull();
    });

    it("recognises cloud managed clusters", () => {
        expect(isCloudManagedDbCluster({ cloud_setup: { cluster_type: "xcloud" } })).toBe(true);
        expect(isCloudManagedDbCluster({ cloud_setup: { cluster_type: "standard" } })).toBe(false);
        expect(isCloudManagedDbCluster({})).toBe(false);
    });
});

describe("getDbNodeSetup", () => {
    it("prefers the values SCT submitted with the config", () => {
        const run = {
            cloud_setup: { db_node: { instance_type: "i4i.large", node_amount: 3 } },
            allocated_resources: [resource("db-node-0-1", "scylla-db", "i8g.large")],
        };
        expect(getDbNodeSetup(run)).toEqual({ instanceType: "i4i.large", nodeAmount: 3 });
    });

    it("derives both values from DB resources when the config had none", () => {
        const run = {
            cloud_setup: { db_node: { instance_type: null, node_amount: null } },
            allocated_resources: [
                resource("loader-node-1", "loader", "c6i.2xlarge"),
                resource("db-node-0-1", "scylla-db", "i8g.large"),
                resource("db-node-0-2", "scylla-db", "i8g.large"),
                resource("db-node-0-3", "scylla-db", "i8g.xlarge"),
                resource("monitor-node-1", "monitor", "t3.large"),
            ],
        };
        expect(getDbNodeSetup(run)).toEqual({ instanceType: "i8g.large, i8g.xlarge", nodeAmount: 3 });
    });

    it("falls back to the legacy name pattern when resource_type is missing", () => {
        const run = {
            cloud_setup: { db_node: {} },
            allocated_resources: [
                { name: "longevity-db-node-1", instance_info: { instance_type: "i3.large" } },
                { name: "longevity-loader-node-1", instance_info: { instance_type: "c5.large" } },
            ],
        };
        expect(getDbNodeSetup(run)).toEqual({ instanceType: "i3.large", nodeAmount: 1 });
    });

    it("returns nulls when nothing is known yet", () => {
        expect(getDbNodeSetup({ cloud_setup: { db_node: {} }, allocated_resources: [] }))
            .toEqual({ instanceType: null, nodeAmount: null });
        expect(getDbNodeSetup({})).toEqual({ instanceType: null, nodeAmount: null });
    });

    it("keeps legacy sentinel values instead of deriving", () => {
        const run = {
            cloud_setup: { db_node: { instance_type: "UNKNOWN", node_amount: -1 } },
            allocated_resources: [resource("db-node-0-1", "scylla-db", "i8g.large")],
        };
        expect(getDbNodeSetup(run)).toEqual({ instanceType: "UNKNOWN", nodeAmount: -1 });
    });
});
