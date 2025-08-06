import NotificationCounter from "./Profile/NotificationCounter.svelte";
import { mount } from "svelte";

let selector = document.querySelector("#notificationCounter");

if (selector) {
    const app = mount(NotificationCounter, {
            target: selector,
            props: {}
        });
}
