import { writable, readable } from "svelte/store";
export const runStore = writable({});
export const polledRuns = readable({}, set => {
    setTimeout(pollTestRuns(set), 10000);

    const interval = setInterval(() => {
        pollTestRuns(set);
    }, 20 * 1000);

    return () => clearInterval(interval);
});

let runCollection = {};

runStore.subscribe((val) => {
    runCollection = val;
})

const pollTestRuns = function (set) {
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
                console.log(res.response);
            } else {
                console.log("Error parsing batch test_run data");
                console.log(res.response);
            }
        });
};