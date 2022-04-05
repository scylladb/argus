import {
    writable
} from "svelte/store";
import {
    apiMethodCall
} from "../Common/ApiUtils";

const releaseRequests = new Set();
const refreshPeriod = 60;

let fetchTimeout;
let oldStats = {};

let fetching = false;
const fetchStats = async function (set) {
    if (fetching) return;
    fetching = true;
    Array.from(releaseRequests)
        .forEach(async releaseRequest => {
            let [releaseName, limitedFetch, forcedFetch] = releaseRequest;
            let params = new URLSearchParams({
                release: releaseName,
                limited: new Number(limitedFetch),
                force: new Number(forcedFetch),
            })
            let result = await apiMethodCall("/api/v1/release/stats?" + params, undefined, "GET");
            if (result.status === "ok") {
                let newStats = {
                    releases: Object.assign(oldStats?.releases ?? {}, result.response.releases)
                };
                set(newStats);
            }
        });
    fetching = false;
};

export const requestReleaseStats = function (releaseName, limited, force) {
    releaseRequests.add([releaseName, limited, force]);
    if (fetchTimeout) {
        clearTimeout(fetchTimeout);
        fetchTimeout = undefined;
    }
    
    fetchTimeout = setTimeout(() => {
        fetchStats((val) => {
            stats.set(val);
        });
    }, 50);
};

export const removeReleaseRequest = function(releaseName) {
    releaseRequests = new Set(Array.from(releaseRequests).filter(req => req[0] != releaseName));
};

export const stats = writable({}, set => {
    fetchTimeout = setTimeout(() => {
        fetchStats(set);
    }, 1000);
    const interval = setInterval(() => {
        fetchStats(set);
    }, refreshPeriod * 1000);

    return () => clearInterval(interval);
});

stats.subscribe(val => {
    oldStats = val;
});
