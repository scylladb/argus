import { writable, readable } from "svelte/store";
let releaseRequestsBody = [];
let releaseGroupRequestsBody = [];
let testRequestsBody = [];

export const releaseRequests = writable([]);
export const groupRequests = writable([]);
export const testRequests = writable([]);
export const stats = readable({}, set => {
    setTimeout(() => {
        fetchStats(set);
    }, 10000);
    const interval = setInterval(() => {
        fetchStats(set)
    }, 20 * 1000);
    
    return () => clearInterval(interval);
});

releaseRequests.subscribe(val => {
    releaseRequestsBody = val;
})

groupRequests.subscribe(val => {
    releaseGroupRequestsBody = val;
})

testRequests.subscribe(val => {
    testRequestsBody = val;
})

const fetchStats = function (set) {
    fetch("/api/v1/stats", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            releases: {
                limit: 20,
                items: releaseRequestsBody,
            },
            groups: {
                limit: 10,
                items: releaseGroupRequestsBody
            },
            tests: {
                limit: 10,
                items: testRequestsBody
            }
        }),
    })
        .then((res) => {
            if (res.status == 200) {
                return res.json();
            } else {
                console.log(res);
            }
        })
        .then((res) => {
            console.log(res);
            if (res.status === "ok") {
                set(res.response);
            }
        });
};
