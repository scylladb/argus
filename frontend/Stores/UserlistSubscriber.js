import {
    readable
} from "svelte/store";

export const userList = readable({}, (set) => {
    setTimeout(() => {
        fetchUsers(set);
    }, 400);

    const interval = setInterval(() => {
        fetchUsers(set);
    }, 300 * 1000);

    return () => clearInterval(interval);
});

const fetchUsers = function (set) {
    return fetch("/api/v1/users")
        .then((res) => {
            if (res.status == 200) {
                return res.json();
            } else {
                console.log("Error fetching users");
                console.log(res);
            }
        })
        .then((res) => {
            if (res.status === "ok") {
                set(res.response);
            } else {
                console.log("Something went wrong...");
                console.log(res);
            }
        });
};
