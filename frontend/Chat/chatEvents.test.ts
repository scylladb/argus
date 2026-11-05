import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectChat, SILENCE_MS } from "./chatEvents";

class FakeEventSource {
    static last: FakeEventSource;
    onmessage: ((event: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = 1;
    closed = false;
    constructor(public url: string) {
        FakeEventSource.last = this;
    }
    close() {
        this.closed = true;
    }
}

describe("connectChat", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal("EventSource", FakeEventSource);
    });
    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it("parses events, stays live through a reconnect, and drops after silence or a closed stream", () => {
        const events: unknown[] = [];
        const live: boolean[] = [];
        const close = connectChat("/events", { onEvent: (e) => events.push(e), onLive: (l) => live.push(l) });
        const source = FakeEventSource.last;

        source.onmessage?.({ data: JSON.stringify({ type: "heartbeat" }) });
        source.onmessage?.({ data: JSON.stringify({ type: "presence", users: ["u"] }) });
        vi.advanceTimersByTime(SILENCE_MS + 1);
        source.onmessage?.({ data: JSON.stringify({ type: "heartbeat" }) });
        source.readyState = 0;
        source.onerror?.();
        source.readyState = 2;
        source.onerror?.();
        close();

        expect(source.url).toBe("/events");
        expect(events).toEqual([{ type: "presence", users: ["u"] }]);
        expect(live).toEqual([true, false, true, false]);
        expect(source.closed).toBe(true);
    });
});
