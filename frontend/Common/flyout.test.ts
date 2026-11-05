import { describe, expect, it } from "vitest";
import { arcKeyframes, landingPoint } from "./flyout";

describe("arcKeyframes", () => {
    it("starts at the source, ends at the target and bends upward on the way", () => {
        const frames = arcKeyframes({ x: 100, y: 500 }, { x: 900, y: 500 }, 10);

        expect(frames).toHaveLength(11);
        expect(frames[0].transform).toBe("translate(100px, 500px) scale(1)");
        expect(frames[10].transform).toBe("translate(900px, 500px) scale(0.6)");
        const middle = /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(frames[5].transform as string)!;
        expect(Number(middle[1])).toBeCloseTo(500);
        expect(Number(middle[2])).toBeLessThan(500);
    });

    it("lifts a short hop less than a long one", () => {
        const lift = (to: number) => {
            const frames = arcKeyframes({ x: 0, y: 400 }, { x: to, y: 400 }, 2);
            return 400 - Number(/, ([-\d.]+)px\)/.exec(frames[1].transform as string)![1]);
        };

        expect(lift(100)).toBeLessThan(lift(1000));
    });
});

describe("landingPoint", () => {
    const viewport = { width: 1600, height: 1000 };

    it("lands near the top of a visible target", () => {
        expect(landingPoint({ left: 1000, top: 300, width: 400 }, viewport)).toEqual({ x: 1200, y: 324 });
    });

    it("stops at the bottom edge when the target is below the screen", () => {
        expect(landingPoint({ left: 1000, top: 2400, width: 400 }, viewport)).toEqual({ x: 1200, y: 976 });
    });

    it("stops at the top edge when the target is above the screen", () => {
        expect(landingPoint({ left: 1000, top: -900, width: 400 }, viewport)).toEqual({ x: 1200, y: 24 });
    });
});
