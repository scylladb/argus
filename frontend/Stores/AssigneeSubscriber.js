import {
    writable
} from "svelte/store";
import {
    sendMessage
} from "./AlertStore";


const assigneeRequests = writable({});
let requestPayload = {};
let fetching = false;
assigneeRequests.subscribe((value) => {
    requestPayload = value;
});

const fetchAssignees = async function (set) {
    if (fetching) return;
    fetching = true;
    try {
        let apiResponse = await fetch("/api/v1/release/schedules/today/assignees", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestPayload),
        });
        let apiJson = await apiResponse.json();
        if (apiJson.status === "ok") {
            set(apiJson.response);
        } else {
            throw apiJson;
        }
    } catch (error) {
        if (error?.status === "error") {
            sendMessage(
                "error",
                `API Error during fetching assignees.\nMessage: ${error.response.arguments[0]}`,
                "AssigneeSubscriber::fetchAssignees"
            );
        } else {
            sendMessage(
                "error",
                "An error occurred refreshing assignees",
                "AssigneeSubscriber::fetchAssignees"
            );
            console.log(error);
        }
    }
    fetching = false;
};

export const requestAssigneesForReleaseGroups = function (release, groups) {
    assigneeRequests.update((value) => {
        let releaseBody = value[release] ?? {};
        let groupSet = new Set([...(releaseBody.groups ?? []), ...groups]);
        releaseBody.groups = Array.from(groupSet.values());
        value[release] = releaseBody;
        return value;
    });

    setTimeout(() => {
        fetchAssignees((value) => assigneeStore.update(() => value));
    }, 250);
};

export const requestAssigneesForReleaseTests = function (release, tests) {
    tests = tests.map((test) => test.build_system_id);
    assigneeRequests.update((value) => {
        let releaseBody = value[release] ?? {};
        let testSet = new Set([...(releaseBody.tests ?? []), ...tests]);
        releaseBody.tests = Array.from(testSet.values());
        value[release] = releaseBody;
        return value;
    });

    setTimeout(() => {
        fetchAssignees((value) => assigneeStore.update(() => value));
    }, 250);
};


export const assigneeStore = writable({}, (set) => {
    setInterval(() => {
        fetchAssignees(set);
    }, 120 * 1000);
});
