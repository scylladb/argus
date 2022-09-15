import { writable, readable } from "svelte/store";
export const testRunStore = writable([]);
export const polledTestRuns = readable({}, set => {
    setTimeout(pollTestRun(set), 10000);

    const interval = setInterval(() => {
        pollTestRun(set);
    }, 120 * 1000);

    return () => clearInterval(interval);
});

let runCollection = [];

testRunStore.subscribe((val) => {
    runCollection = val;
})

const pollTestRun = function (set) {
    let params = new URLSearchParams({
        runs: runCollection,
    }).toString();
    fetch("/api/v1/test_run/poll?" + params)
        .then((res) => {
            if (res.status == 200) {
                return res.json();
            } else {
                console.log("Error during batch test_run data fetch");
            }
        })
        .then((res) => {
            if (res.status == "ok") {
                set(res.response);
            } else {
                console.log("Error parsing batch test_run data");
                console.log(res.response);
            }
        });
};
