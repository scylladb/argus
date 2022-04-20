import NotificationCounter from "./Profile/NotificationCounter.svelte";

let selector = document.querySelector("#notificationCounter");

if (selector) {
    const app = new NotificationCounter({
        target: selector,
        props: {}
    });
}
