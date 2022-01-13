import { writable } from "svelte/store";
export const runStore = writable({});
export const TestRunsEventListener = writable({
    type: "init",
    args: []
});
export const polledRuns = writable({}, set => {

    const interval = setInterval(() => {
        pollTestRuns(set);
    }, 20 * 1000);

    return () => clearInterval(interval);
});

let runCollection = {};
let fetching = false;
runStore.subscribe((val) => {
    runCollection = val;
});

TestRunsEventListener.subscribe(value => {
    switch (value.type) {
        case "init":
            console.log("TestRunsSubscriber init");
            break;
        case "fetch":
            console.log("fetch");
            setTimeout(() => {
                pollTestRuns((fetchedRuns) => {
                    polledRuns.update(() => fetchedRuns);
                });
            }, 150);
            break;
        case "unsubscribe":
            delete runCollection[value.id];
            break;
        default:
            break;
    }
});

const pollTestRuns = function (set) {
    if (fetching) return;
    fetching = true;
    fetch("/api/v1/test_runs/poll", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            limit: 10,
            runs: runCollection
        }),
    })
        .then((res) => {
            if (res.status == 200) {
                return res.json();
            } else {
                console.log("Error during batch test_run fetch");
            }
        })
        .then((res) => {
            if (res.status == "ok") {
                set(res.response);
                fetching = false;
                console.log(res.response);
            } else {
                console.log("Error parsing batch test_run data");
                console.log(res.response);
            }
        });
};
