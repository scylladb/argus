import { PLUGIN_NAMES } from "./PluginNames";

export const newIssueDestinations = {
    [PLUGIN_NAMES.SCT]: [
        {
            name: "ScyllaDB",
            url: "https://github.com/scylladb/scylla",
        },
        {
            "name": "Scylla Enterprise",
            "url": "https://github.com/scylladb/scylla-enterprise",
        },
        {
            name: "Scylla Cluster Tests",
            url: "https://github.com/scylladb/scylla-cluster-tests",
        },
    ],
    [PLUGIN_NAMES.SIRENADA]: [
        {
            name: "Siren Tests",
            url: "https://github.com/scylladb/siren-tests",
        },
        {
            name: "Siren",
            url: "https://github.com/scylladb/siren",
        },
        {
            name: "Siren Frontend",
            url: "https://github.com/scylladb/siren-frontend",
        },
        {
            name: "Siren Devops",
            url: "https://github.com/scylladb/siren-devops",
        },
    ],
};
