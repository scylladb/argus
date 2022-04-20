import {
    readable
} from "svelte/store";
import { apiMethodCall } from "../Common/ApiUtils";

const fetchReleases = async function (cb) {
    let result = await apiMethodCall("/api/v1/releases", undefined, "GET");
    if (result.status === "ok") {
        cb(result.response);
    }
};

const fetchGroups = async function (cb) {
    let result = await apiMethodCall("/api/v1/groups", undefined, "GET");
    if (result.status === "ok") {
        cb(result.response);
    }
};

const fetchTests = async function (cb) {
    let result = await apiMethodCall("/api/v1/tests", undefined, "GET");
    if (result.status === "ok") {
        cb(result.response);
    }
};


export const allReleases = readable(undefined, function (set) {

    fetchReleases(set);

    setInterval(
        () => {
            fetchReleases(set);
        }, 120 * 1000
    );
});

export const allGroups = readable(undefined, function (set) {
    fetchGroups(set);

    setInterval(
        () => {
            fetchGroups(set);
        }, 120 * 1000
    );
});


export const allTests = readable(undefined, function (set) {
    fetchTests(set);

    setInterval(
        () => {
            fetchTests(set);
        }, 120 * 1000
    );
});
