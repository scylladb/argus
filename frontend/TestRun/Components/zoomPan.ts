export type View = { scale: number; x: number; y: number };

export type Bounds = {
    stageWidth: number;
    stageHeight: number;
    imageWidth: number;
    imageHeight: number;
    maxScale: number;
};

type Point = { x: number; y: number };

export const FIT: Readonly<View> = Object.freeze({ scale: 1, x: 0, y: 0 });

const SMALLEST_MAX_SCALE = 4;

export function measure(stage: HTMLElement, image: HTMLImageElement): Bounds {
    const imageWidth = image.offsetWidth;
    return {
        stageWidth: stage.clientWidth,
        stageHeight: stage.clientHeight,
        imageWidth,
        imageHeight: image.offsetHeight,
        maxScale: Math.max(SMALLEST_MAX_SCALE, imageWidth > 0 ? image.naturalWidth / imageWidth : 1),
    };
}

const hasLayout = (bounds: Bounds) =>
    bounds.stageWidth > 0 && bounds.stageHeight > 0 && bounds.imageWidth > 0 && bounds.imageHeight > 0;

const clampScale = (scale: number, bounds: Bounds) => Math.min(bounds.maxScale, Math.max(1, scale));

const clampOffset = (value: number, limit: number) => (limit > 0 ? Math.max(-limit, Math.min(limit, value)) : 0);

export function clampView(view: View, bounds: Bounds): View {
    if (!hasLayout(bounds)) {
        return view;
    }
    const scale = clampScale(view.scale, bounds);
    return {
        scale,
        x: clampOffset(view.x, (bounds.imageWidth * scale - bounds.stageWidth) / 2),
        y: clampOffset(view.y, (bounds.imageHeight * scale - bounds.stageHeight) / 2),
    };
}

export function zoomAt(view: View, factor: number, point: Point, bounds: Bounds): View {
    if (!hasLayout(bounds)) {
        return view;
    }
    const scale = clampScale(view.scale * factor, bounds);
    const ratio = scale / view.scale;
    return clampView({ scale, x: point.x - (point.x - view.x) * ratio, y: point.y - (point.y - view.y) * ratio }, bounds);
}

export function panBy(view: View, dx: number, dy: number, bounds: Bounds): View {
    return clampView({ scale: view.scale, x: view.x + dx, y: view.y + dy }, bounds);
}

export type ZoomPanParams = {
    view: () => View;
    setView: (view: View) => void;
    image: () => HTMLImageElement | undefined;
    onTap: () => void;
    onSwipe: (direction: "prev" | "next") => void;
};

const TAP_SLOP = 4;
const SWIPE_MIN = 50;
const WHEEL_LINE = 16;
const WHEEL_RATE = 0.002;
const PINCH_RATE = 0.01;

const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const midpoint = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

export function zoomPan(node: HTMLElement, params: ZoomPanParams): { destroy(): void } {
    const pointers = new Map<number, Point>();
    let pendingTap = false;
    let gesture: {
        start: Point;
        target: EventTarget | null;
        pointerType: string;
        travelled: number;
        dragging: boolean;
        pinched: boolean;
    } | null = null;

    const bounds = () => {
        const image = params.image();
        return image ? measure(node, image) : null;
    };

    const pointAt = (clientX: number, clientY: number): Point => {
        const rect = node.getBoundingClientRect();
        return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
    };

    const onWheel = (event: WheelEvent) => {
        event.preventDefault();
        const current = bounds();
        if (!current) {
            return;
        }
        let delta = event.deltaY;
        if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
            delta *= WHEEL_LINE;
        } else if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
            delta *= current.stageHeight;
        }
        const factor = Math.min(2, Math.max(0.5, Math.exp(-delta * (event.ctrlKey ? PINCH_RATE : WHEEL_RATE))));
        params.setView(zoomAt(params.view(), factor, pointAt(event.clientX, event.clientY), current));
    };

    const onPointerDown = (event: PointerEvent) => {
        pendingTap = false;
        if (event.button !== 0 || (event.target instanceof Element && event.target.closest("button"))) {
            return;
        }
        const position = { x: event.clientX, y: event.clientY };
        if (pointers.size === 0) {
            gesture = { start: position, target: event.target, pointerType: event.pointerType, travelled: 0, dragging: false, pinched: false };
        } else if (gesture) {
            gesture.pinched = true;
            if (gesture.dragging) {
                node.setPointerCapture?.(event.pointerId);
            }
        }
        pointers.set(event.pointerId, position);
    };

    const onPointerMove = (event: PointerEvent) => {
        const last = pointers.get(event.pointerId);
        if (!last || !gesture) {
            return;
        }
        const position = { x: event.clientX, y: event.clientY };
        gesture.travelled = Math.max(gesture.travelled, distance(position, gesture.start));
        if (!gesture.dragging && gesture.travelled >= TAP_SLOP) {
            gesture.dragging = true;
            for (const id of pointers.keys()) {
                node.setPointerCapture?.(id);
            }
        }
        const current = bounds();
        if (current && pointers.size === 1) {
            params.setView(panBy(params.view(), position.x - last.x, position.y - last.y, current));
        } else if (current && pointers.size === 2) {
            const other = [...pointers.entries()].find(([id]) => id !== event.pointerId)?.[1] as Point;
            const before = distance(last, other);
            if (before > 0) {
                const from = midpoint(last, other);
                const to = midpoint(position, other);
                const zoomed = zoomAt(params.view(), distance(position, other) / before, pointAt(from.x, from.y), current);
                params.setView(panBy(zoomed, to.x - from.x, to.y - from.y, current));
            }
        }
        pointers.set(event.pointerId, position);
    };

    const onPointerEnd = (event: PointerEvent, cancelled: boolean) => {
        if (!pointers.delete(event.pointerId) || pointers.size > 0 || !gesture) {
            return;
        }
        const finished = gesture;
        gesture = null;
        if (cancelled || finished.pinched) {
            return;
        }
        if (!finished.dragging) {
            pendingTap = finished.target === node;
            return;
        }
        const dx = event.clientX - finished.start.x;
        const dy = event.clientY - finished.start.y;
        if (finished.pointerType === "touch" && params.view().scale === 1 && Math.abs(dx) > SWIPE_MIN && Math.abs(dx) > Math.abs(dy)) {
            params.onSwipe(dx < 0 ? "next" : "prev");
        }
    };

    const onPointerUp = (event: PointerEvent) => onPointerEnd(event, false);
    const onPointerCancel = (event: PointerEvent) => onPointerEnd(event, true);

    const onClick = () => {
        if (pendingTap) {
            pendingTap = false;
            params.onTap();
        }
    };

    const onDoubleClick = (event: MouseEvent) => {
        const image = params.image();
        if (!image || event.target !== image) {
            return;
        }
        const view = params.view();
        if (view.scale > 1) {
            params.setView(FIT);
            return;
        }
        const current = measure(node, image);
        const actual = current.imageWidth > 0 ? image.naturalWidth / current.imageWidth : 1;
        params.setView(zoomAt(view, Math.max(2, actual), pointAt(event.clientX, event.clientY), current));
    };

    const onResize = () => {
        const current = bounds();
        if (current) {
            params.setView(clampView(params.view(), current));
        }
    };

    const preventDefault = (event: Event) => event.preventDefault();

    node.addEventListener("wheel", onWheel, { passive: false });
    node.addEventListener("pointerdown", onPointerDown);
    node.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);
    node.addEventListener("click", onClick);
    node.addEventListener("dblclick", onDoubleClick);
    node.addEventListener("gesturestart", preventDefault);
    node.addEventListener("gesturechange", preventDefault);
    window.addEventListener("resize", onResize);

    return {
        destroy() {
            node.removeEventListener("wheel", onWheel);
            node.removeEventListener("pointerdown", onPointerDown);
            node.removeEventListener("pointermove", onPointerMove);
            window.removeEventListener("pointerup", onPointerUp);
            window.removeEventListener("pointercancel", onPointerCancel);
            node.removeEventListener("click", onClick);
            node.removeEventListener("dblclick", onDoubleClick);
            node.removeEventListener("gesturestart", preventDefault);
            node.removeEventListener("gesturechange", preventDefault);
            window.removeEventListener("resize", onResize);
        },
    };
}
