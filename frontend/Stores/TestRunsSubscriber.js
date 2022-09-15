import { writable } from "svelte/store";
export const runStore = writable([]);
export const TestRunsEventListener = writable({
    type: "init",
    args: []
});
export const polledRuns = writable({}, set => {

    const interval = setInterval(() => {
        pollTestRuns(set);
    }, 120 * 1000);

    return () => clearInterval(interval);
});

let runCollection = [];
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
    let params = new URLSearchParams({
        limit: 10,
    }).toString();
    let runs = runCollection.map(val => {
        let [buildId, additionalIds] = val;
        let idsQs = additionalIds.map(val => `additionalRuns${buildId}[]=${val}`);
        return [`runs[]=${buildId}`, ...idsQs].join("&");
    }).join("&");
    fetch("/api/v1/test_runs/poll?" + params + "&" + runs)
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
            } else {
                console.log("Error parsing batch test_run data");
                console.log(res.response);
            }
        });
};
