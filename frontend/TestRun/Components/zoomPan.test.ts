import { describe, it, expect, vi, afterEach } from "vitest";
import { FIT, clampView, measure, panBy, zoomAt, zoomPan, type Bounds, type View } from "./zoomPan";

const BOUNDS: Bounds = { stageWidth: 1000, stageHeight: 800, imageWidth: 1000, imageHeight: 562.5, maxScale: 4 };
const NO_LAYOUT: Bounds = { stageWidth: 0, stageHeight: 0, imageWidth: 0, imageHeight: 0, maxScale: 4 };

const size = (element: HTMLElement, sizes: Record<string, number>) => {
    for (const [name, value] of Object.entries(sizes)) {
        Object.defineProperty(element, name, { configurable: true, value });
    }
    return element;
};

describe("clampView", () => {
    it("keeps a fit view centred when the image is smaller than the surface", () => {
        expect(clampView({ scale: 1, x: 120, y: -40 }, BOUNDS)).toEqual(FIT);
    });

    it("limits the pan to the overflow of the zoomed image", () => {
        expect(clampView({ scale: 2, x: 900, y: -900 }, BOUNDS)).toEqual({ scale: 2, x: 500, y: -162.5 });
    });

    it("limits the scale to the fit and the maximum", () => {
        expect(clampView({ scale: 0.3, x: 0, y: 0 }, BOUNDS).scale).toBe(1);
        expect(clampView({ scale: 9, x: 0, y: 0 }, BOUNDS).scale).toBe(4);
    });

    it("returns the view unchanged when the surface has no layout", () => {
        const view = { scale: 3, x: 50, y: 20 };
        expect(clampView(view, NO_LAYOUT)).toEqual(view);
    });
});

describe("zoomAt", () => {
    it("keeps the point under the pointer fixed when zooming in", () => {
        expect(zoomAt(FIT, 2, { x: 300, y: 0 }, BOUNDS)).toEqual({ scale: 2, x: -300, y: 0 });
    });

    it("keeps the anchor across a partial zoom out", () => {
        expect(zoomAt({ scale: 2, x: -300, y: 0 }, 0.75, { x: 0, y: 0 }, BOUNDS)).toEqual({ scale: 1.5, x: -225, y: 0 });
    });

    it("re-centres when zooming back to fit", () => {
        expect(zoomAt({ scale: 2, x: -300, y: 0 }, 0.5, { x: 0, y: 0 }, BOUNDS)).toEqual(FIT);
    });

    it("uses the clamped scale for the anchor at the maximum", () => {
        const atMax = { scale: 4, x: -100, y: 0 };
        expect(zoomAt(atMax, 2, { x: 300, y: 0 }, BOUNDS)).toEqual(atMax);
    });

    it("leaves the view alone when the surface has no layout", () => {
        expect(zoomAt(FIT, 2, { x: 300, y: 0 }, NO_LAYOUT)).toEqual(FIT);
    });
});

describe("panBy", () => {
    it("pans by the delta and stops at the edge", () => {
        expect(panBy({ scale: 2, x: 0, y: 0 }, -120, 30, BOUNDS)).toEqual({ scale: 2, x: -120, y: 30 });
        expect(panBy({ scale: 2, x: 450, y: 0 }, 200, 0, BOUNDS)).toEqual({ scale: 2, x: 500, y: 0 });
    });

    it("does not move a fitted image", () => {
        expect(panBy(FIT, 50, 50, BOUNDS)).toEqual(FIT);
    });
});

describe("measure", () => {
    it("reads the sizes from the elements and keeps four as the smallest maximum", () => {
        const stage = size(document.createElement("div"), { clientWidth: 1000, clientHeight: 800 });
        const image = size(document.createElement("img"), { offsetWidth: 1000, offsetHeight: 562.5, naturalWidth: 1920 });
        expect(measure(stage, image as HTMLImageElement)).toEqual(BOUNDS);
    });

    it("lets a tall capture reach its actual pixels", () => {
        const stage = size(document.createElement("div"), { clientWidth: 1000, clientHeight: 800 });
        const image = size(document.createElement("img"), { offsetWidth: 54, offsetHeight: 800, naturalWidth: 1080 });
        expect(measure(stage, image as HTMLImageElement).maxScale).toBe(20);
    });

    it("falls back to four when the image has no layout", () => {
        const stage = size(document.createElement("div"), { clientWidth: 1000, clientHeight: 800 });
        const image = size(document.createElement("img"), { offsetWidth: 0, offsetHeight: 0, naturalWidth: 1920 });
        expect(measure(stage, image as HTMLImageElement).maxScale).toBe(4);
    });
});

describe("zoomPan action", () => {
    const rect = (width: number, height: number) =>
        ({ left: 0, top: 0, right: width, bottom: height, width, height, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;

    const mount = (initial: View = FIT) => {
        const node = size(document.createElement("div"), { clientWidth: 1000, clientHeight: 800 });
        node.getBoundingClientRect = () => rect(node.clientWidth, node.clientHeight);
        const image = size(document.createElement("img"), { offsetWidth: 1000, offsetHeight: 562.5, naturalWidth: 1920 });
        const button = document.createElement("button");
        node.append(button, image);
        document.body.append(node);
        let current = initial;
        const setView = vi.fn((next: View) => {
            current = next;
        });
        const onTap = vi.fn();
        const onSwipe = vi.fn();
        const action = zoomPan(node, { view: () => current, setView, image: () => image as HTMLImageElement, onTap, onSwipe });
        return { node, image, button, setView, onTap, onSwipe, view: () => current, destroy: action.destroy };
    };

    type WheelInit = ConstructorParameters<typeof WheelEvent>[1];
    type PointerInit = ConstructorParameters<typeof PointerEvent>[1];

    const wheel = (target: Element, init: WheelInit) => {
        const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 500, clientY: 400, ...init });
        target.dispatchEvent(event);
        return event;
    };

    const pointer = (type: string, target: Element, init: PointerInit) =>
        target.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse", ...init }));

    const tap = (target: Element, at: [number, number], init: PointerInit = {}) => {
        pointer("pointerdown", target, { clientX: at[0], clientY: at[1], ...init });
        pointer("pointerup", target, { clientX: at[0] + 1, clientY: at[1] + 2, ...init });
        target.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: at[0] + 1, clientY: at[1] + 2 }));
    };

    const drag = (target: Element, from: [number, number], to: [number, number], init: PointerInit = {}) => {
        pointer("pointerdown", target, { clientX: from[0], clientY: from[1], ...init });
        pointer("pointermove", target, { clientX: to[0], clientY: to[1], ...init });
        pointer("pointerup", target, { clientX: to[0], clientY: to[1], ...init });
    };

    afterEach(() => {
        document.body.innerHTML = "";
    });

    it("zooms around the pointer on a wheel notch and prevents the default", () => {
        const { node, view } = mount();

        const event = wheel(node, { deltaY: -100, clientX: 800, clientY: 400 });

        expect(event.defaultPrevented).toBe(true);
        expect(view().scale).toBeCloseTo(Math.exp(0.2), 6);
        expect(view().x).toBeCloseTo(300 * (1 - Math.exp(0.2)), 6);
        expect(view().y).toBe(0);
    });

    it("zooms by sixteen pixels per line on a line-mode wheel", () => {
        const { node, view } = mount();

        wheel(node, { deltaY: -5, deltaMode: 1 });

        expect(view().scale).toBeCloseTo(Math.exp(0.16), 6);
    });

    it("zooms faster with ctrl held, as a trackpad pinch sends it", () => {
        const plain = mount();
        const pinch = mount();

        wheel(plain.node, { deltaY: -20 });
        wheel(pinch.node, { deltaY: -20, ctrlKey: true });

        expect(pinch.view().scale).toBeGreaterThan(plain.view().scale);
        expect(pinch.view().scale).toBeCloseTo(Math.exp(0.2), 6);
    });

    it("pans the zoomed image on a left-button drag and ignores another button", () => {
        const { node, view, setView } = mount({ scale: 2, x: 0, y: 0 });

        drag(node, [500, 400], [450, 380]);
        expect(view()).toEqual({ scale: 2, x: -50, y: -20 });

        setView.mockClear();
        drag(node, [500, 400], [400, 400], { button: 2 });
        expect(setView).not.toHaveBeenCalled();
    });

    it("pinches around the midpoint of two pointers and carries on as a pan when one lifts", () => {
        const { node, view } = mount();

        pointer("pointerdown", node, { pointerId: 1, pointerType: "touch", clientX: 400, clientY: 400 });
        pointer("pointerdown", node, { pointerId: 2, pointerType: "touch", clientX: 600, clientY: 400 });
        pointer("pointermove", node, { pointerId: 2, pointerType: "touch", clientX: 800, clientY: 400 });
        expect(view()).toEqual({ scale: 2, x: 100, y: 0 });

        pointer("pointerup", node, { pointerId: 1, pointerType: "touch", clientX: 400, clientY: 400 });
        pointer("pointermove", node, { pointerId: 2, pointerType: "touch", clientX: 820, clientY: 410 });
        expect(view()).toEqual({ scale: 2, x: 120, y: 10 });
    });

    it("reports a tap on the backdrop and nothing else", () => {
        const { node, image, button, onTap } = mount();

        tap(node, [100, 100]);
        expect(onTap).toHaveBeenCalledTimes(1);

        tap(image, [100, 100]);
        tap(button, [100, 100]);
        drag(node, [100, 100], [120, 100]);
        node.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 120, clientY: 100 }));
        expect(onTap).toHaveBeenCalledTimes(1);
    });

    it("reports the tap on the click that follows it, not on the pointerup", () => {
        const { node, onTap } = mount();

        pointer("pointerdown", node, { clientX: 100, clientY: 100 });
        pointer("pointerup", node, { clientX: 100, clientY: 100 });
        expect(onTap).not.toHaveBeenCalled();

        node.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 100, clientY: 100 }));
        expect(onTap).toHaveBeenCalledTimes(1);
    });

    it("ends a mouse press that is released outside the surface", () => {
        const { node, onTap } = mount({ scale: 2, x: 0, y: 0 });

        pointer("pointerdown", node, { clientX: 500, clientY: 400 });
        pointer("pointermove", node, { clientX: 501, clientY: 400 });
        pointer("pointerup", document.body, { clientX: 501, clientY: 10 });

        tap(node, [100, 100]);
        expect(onTap).toHaveBeenCalledTimes(1);
    });

    it("reports a touch swipe at the fitted size and ignores a mouse drag there", () => {
        const { node, onSwipe } = mount();

        drag(node, [600, 400], [500, 410], { pointerType: "touch" });
        expect(onSwipe).toHaveBeenLastCalledWith("next");

        drag(node, [400, 400], [520, 420], { pointerType: "touch" });
        expect(onSwipe).toHaveBeenLastCalledWith("prev");

        drag(node, [600, 400], [500, 400]);
        expect(onSwipe).toHaveBeenCalledTimes(2);
    });

    it("pans instead of swiping when the image is zoomed", () => {
        const { node, onSwipe, view } = mount({ scale: 2, x: 0, y: 0 });

        drag(node, [600, 400], [500, 400], { pointerType: "touch" });

        expect(onSwipe).not.toHaveBeenCalled();
        expect(view()).toEqual({ scale: 2, x: -100, y: 0 });
    });

    it("toggles between the fitted size and the actual pixels on a double-click on the image", () => {
        const { image, view } = mount();

        image.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 800, clientY: 400 }));
        expect(view()).toEqual({ scale: 2, x: -300, y: 0 });

        image.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 800, clientY: 400 }));
        expect(view()).toEqual(FIT);
    });

    it("re-clamps the view when the window is resized", () => {
        const { node, image, view } = mount({ scale: 2, x: 500, y: 0 });

        size(node, { clientWidth: 500 });
        size(image, { offsetWidth: 500 });
        window.dispatchEvent(new Event("resize"));

        expect(view()).toEqual({ scale: 2, x: 250, y: 0 });
    });

    it("captures the pointer only once a drag starts, so a click keeps its target", () => {
        const { node } = mount({ scale: 2, x: 0, y: 0 });
        const capture = vi.fn();
        (node as HTMLElement & { setPointerCapture: typeof capture }).setPointerCapture = capture;

        drag(node, [100, 100], [101, 102]);
        expect(capture).not.toHaveBeenCalled();

        drag(node, [100, 100], [160, 100], { pointerId: 7 });
        expect(capture).toHaveBeenCalledWith(7);
    });

    it("stops listening after destroy", () => {
        const { node, setView, destroy } = mount();

        destroy();
        wheel(node, { deltaY: -100 });
        window.dispatchEvent(new Event("resize"));

        expect(setView).not.toHaveBeenCalled();
    });
});
