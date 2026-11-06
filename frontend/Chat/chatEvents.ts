import type { ServerEvent } from "./types";

export const SILENCE_MS = 30_000;
const CLOSED = 2;

export interface ChatEventHandlers {
    onEvent: (event: ServerEvent) => void;
    onLive: (live: boolean) => void;
}

/** Follows the chat's server-sent events. The server ends each stream after a
 * short lifetime and EventSource reconnects into a fresh snapshot, so a routine
 * reconnect keeps the chat live. `onLive(false)` fires when the browser gives up,
 * or when not even a heartbeat arrived for SILENCE_MS, so the caller can poll. */
export const connectChat = (url: string, handlers: ChatEventHandlers): (() => void) => {
    const source = new EventSource(url);
    let live = false;
    let silence: ReturnType<typeof setTimeout> | undefined;

    const setLive = (value: boolean) => {
        if (value !== live) {
            live = value;
            handlers.onLive(value);
        }
    };
    const armSilence = () => {
        clearTimeout(silence);
        silence = setTimeout(() => setLive(false), SILENCE_MS);
    };

    source.onmessage = (message: MessageEvent | { data: string }) => {
        setLive(true);
        armSilence();
        const event = JSON.parse(message.data) as ServerEvent;
        if (event.type !== "heartbeat") handlers.onEvent(event);
    };
    source.onerror = () => {
        if (source.readyState === CLOSED) setLive(false);
    };

    return () => {
        clearTimeout(silence);
        source.close();
    };
};
