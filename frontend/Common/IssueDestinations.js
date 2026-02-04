import { PLUGIN_NAMES } from "./PluginNames";

const JIRA_SERVER = "https://scylladb.atlassian.net";

const getJiraCreateUrl = (pid) => {
    return `${JIRA_SERVER}/secure/CreateIssue.jspa?pid=${pid}`;
};

export const newIssueDestinations = {
    [PLUGIN_NAMES.SCT]: [
        {
            name: "ScyllaDB",
            url: getJiraCreateUrl("10408"),
        },
        {
            name: "Scylla Cluster Tests",
            url: getJiraCreateUrl("10781"),
        },
    ],
    [PLUGIN_NAMES.SIRENADA]: [
        {
            name: "Scylla Cloud",
            url: getJiraCreateUrl("10612"),
        },
    ],
};
