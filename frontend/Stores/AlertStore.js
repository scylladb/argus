import { writable } from "svelte/store";
import { v4 as uuidv4 } from "uuid";

export const alertStore = writable({});

export const sendMessage = function (type, message, source = "") {
    alertStore.update(() => {
        return {
            id: uuidv4(),
            type: type,
            message: message,
            source: source,
        };
    });
};
