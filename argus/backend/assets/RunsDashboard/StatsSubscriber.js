import { writable } from "svelte/store";
let releaseRequestsBody = [];
let releaseGroupRequestsBody = [];
let testRequestsBody = [];
let releaseBurst = 0;
let groupBurst = 0;
let fetching = false;

const checkBurst = function() {
    if (groupBurst > 7) {
        setTimeout(() => {
            fetchStats((new_stats) => {
                stats.update(() => new_stats);
            });
        }, 200);
        groupBurst = 0;
        return;
    }

    if (releaseBurst > 5) {
        setTimeout(() => {
            fetchStats((new_stats) => {
                stats.update(() => new_stats);
            });
        }, 200);
        releaseBurst = 0;
        return;
    }
};

export const releaseRequests = writable([]);
export const groupRequests = writable([]);
export const testRequests = writable([]);
export const stats = writable({}, set => {
    setTimeout(() => {
        fetchStats(set);
    }, 200);
    const interval = setInterval(() => {
        fetchStats(set);
    }, 20 * 1000);

    return () => clearInterval(interval);
});

releaseRequests.subscribe(val => {
    releaseRequestsBody = val;
    releaseBurst++;
    checkBurst();
});

groupRequests.subscribe(val => {
    releaseGroupRequestsBody = val;
    groupBurst++;
    checkBurst();
});

testRequests.subscribe(val => {
    testRequestsBody = val;
});

const fetchStats = function (set) {
    if (fetching) return;
    let body = {};
    releaseRequestsBody.forEach(element => {
        body[element] = {
            tests: [],
            groups: []
        };
    });

    releaseGroupRequestsBody.forEach(element => {
        let [release, group] = element;
        body[release].groups.push(group);
    });

    testRequestsBody.forEach(element => {
        let [release, _, test] = element;
        body[release].tests.push(test);
    });

    fetching = true;
    fetch("/api/v1/stats", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
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
                fetching = false;
            }
        });
};
