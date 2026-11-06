export interface Point {
    x: number;
    y: number;
}

export interface Flight {
    id: number;
    from: Point;
    to: Point;
    label: string;
}

const EDGE = 24;
const MAX_LIFT = 220;
const LIFT_SHARE = 0.35;
const END_SCALE = 0.6;
const FLIGHT_MS = 650;
const PING_MS = 500;

export function arcKeyframes(from: Point, to: Point, steps = 24): Keyframe[] {
    const distance = Math.hypot(to.x - from.x, to.y - from.y);
    const lift = Math.min(MAX_LIFT, distance * LIFT_SHARE);
    const control = { x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - lift };
    return Array.from({ length: steps + 1 }, (_, index) => {
        const t = index / steps;
        const x = (1 - t) ** 2 * from.x + 2 * (1 - t) * t * control.x + t ** 2 * to.x;
        const y = (1 - t) ** 2 * from.y + 2 * (1 - t) * t * control.y + t ** 2 * to.y;
        const scale = 1 - (1 - END_SCALE) * t;
        return { transform: `translate(${+x.toFixed(2)}px, ${+y.toFixed(2)}px) scale(${+scale.toFixed(3)})` };
    });
}

export function landingPoint(
    rect: { left: number; top: number; width: number },
    viewport: { width: number; height: number },
): Point {
    const clamp = (value: number, max: number) => Math.min(Math.max(value, EDGE), max - EDGE);
    return { x: clamp(rect.left + rect.width / 2, viewport.width), y: clamp(rect.top + EDGE, viewport.height) };
}

export function prefersReducedMotion(): boolean {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function play(node: HTMLElement, frames: Keyframe[], duration: number, easing: string, done: () => void) {
    if (typeof node.animate !== "function") {
        queueMicrotask(done);
        return () => {};
    }
    const animation = node.animate(frames, { duration, easing, fill: "forwards" });
    animation.onfinish = done;
    return () => animation.cancel();
}

export function flyAlongArc(node: HTMLElement, params: { flight: Flight; onLanded: () => void }) {
    const { flight, onLanded } = params;
    if (prefersReducedMotion()) {
        node.hidden = true;
        queueMicrotask(onLanded);
        return {};
    }
    const stop = play(node, arcKeyframes(flight.from, flight.to), FLIGHT_MS, "cubic-bezier(0.45, 0, 0.55, 1)", onLanded);
    return { destroy: stop };
}

export function ping(node: HTMLElement, params: { at: Point; onDone: () => void }) {
    const { at, onDone } = params;
    const place = `translate(${at.x}px, ${at.y}px)`;
    const frames = [
        { transform: `${place} scale(0.4)`, opacity: 0.9 },
        { transform: `${place} scale(2.2)`, opacity: 0 },
    ];
    const stop = play(node, frames, PING_MS, "ease-out", onDone);
    return { destroy: stop };
}
