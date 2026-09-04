// Helpers for the "System Information" block of an SCT run.
//
// Scylla Cloud (xcloud) runs carry two extra descriptors on cloud_setup, and for "xcloud"
// clusters the DB node instance type / amount are chosen by Scylla Cloud's scaling policy, so
// they are unknown at submission time and get derived from the DB node resources SCT registers.

export const CLUSTER_TYPE_LABELS = {
    standard: "Standard",
    xcloud: "XCloud",
};

export const NETWORK_TYPE_LABELS = {
    public: "Public",
    "private-vpc": "Private (VPC peering)",
    "private-tgw": "Private (Transit Gateway)",
};

export const clusterTypeLabel = function (clusterType) {
    if (!clusterType) return null;
    return CLUSTER_TYPE_LABELS[clusterType] ?? clusterType;
};

export const networkTypeLabel = function (networkType) {
    if (!networkType) return null;
    return NETWORK_TYPE_LABELS[networkType] ?? networkType;
};

/** True when the DB node shape is picked by Scylla Cloud rather than configured in SCT. */
export const isCloudManagedDbCluster = function (testRun) {
    return testRun?.cloud_setup?.cluster_type === "xcloud";
};

// Mirrors SCT's `"db" in node_type` (scylla-db, cs-db...), with the legacy name check as fallback.
const isDbResource = function (resource) {
    if (resource?.resource_type) {
        return resource.resource_type.includes("db");
    }
    return /-db-node/.test(resource?.name ?? "");
};

/**
 * DB node instance type and amount for a run: cloud_setup values when SCT knew them, otherwise
 * derived from the registered DB node resources. Either value is null when nothing is known yet.
 */
export const getDbNodeSetup = function (testRun) {
    const dbNode = testRun?.cloud_setup?.db_node ?? {};
    let instanceType = dbNode.instance_type ?? null;
    let nodeAmount = dbNode.node_amount ?? null;
    if (instanceType && nodeAmount !== null) {
        return { instanceType, nodeAmount };
    }

    const dbResources = (testRun?.allocated_resources ?? []).filter(isDbResource);
    if (dbResources.length === 0) {
        return { instanceType, nodeAmount };
    }
    if (!instanceType) {
        const types = new Set(dbResources.map((res) => res.instance_info?.instance_type).filter(Boolean));
        instanceType = Array.from(types).sort().join(", ") || null;
    }
    if (nodeAmount === null) {
        nodeAmount = dbResources.length;
    }
    return { instanceType, nodeAmount };
};
