import {
    writable
} from "svelte/store";


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
                `API Error when fetching release groups.\nMessage: ${error.response.arguments[0]}`
            );
        } else {
            sendMessage(
                "error",
                "An error occurred refreshing assignees"
            );
            console.log(error);
        }
    }
    fetching = false;
}

export const requestAssigneesForReleaseGroups = function (release, groups) {
    assigneeRequests.update((value) => {
        let releaseBody = value[release] ?? {};
        releaseBody.groups = groups;
        value[release] = releaseBody;
        return value;
    });

    setTimeout(() => {
        fetchAssignees((value) => assigneeStore.update(() => value));
    }, 250);
}

export const assigneeStore = writable({}, (set) => {
    setInterval(() => {
        fetchAssignees(set);
    }, 120 * 1000);
});
