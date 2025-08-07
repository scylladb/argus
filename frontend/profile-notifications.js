import NotificationsReader from "./Profile/NotificationsReader.svelte";
import { mount } from "svelte";

const app = mount(NotificationsReader, {
    target: document.querySelector("#notificationsContainer")
});
