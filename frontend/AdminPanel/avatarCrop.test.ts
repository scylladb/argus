import { describe, expect, it } from "vitest";
import { MAX_ZOOM, centeredCrop, clampCrop, sourceSquare, zoomCrop } from "./avatarCrop";

const wide = { width: 480, height: 240 };

const expectSquare = (actual: { x: number; y: number; size: number }, expected: typeof actual) =>
    (["x", "y", "size"] as const).forEach((key) => expect(actual[key]).toBeCloseTo(expected[key]));

describe("avatarCrop", () => {
    it("centers a wide picture so its height fills the square", () => {
        const crop = centeredCrop(wide, 240);

        expect(crop.zoom).toBe(1);
        expectSquare({ x: crop.x, y: crop.y, size: 0 }, { x: -120, y: 0, size: 0 });
        expectSquare(sourceSquare(crop, wide, 240), { x: 120, y: 0, size: 240 });
    });

    it("never moves the picture off the square or zooms out of range", () => {
        expect(clampCrop({ zoom: 1, x: 50, y: -50 }, wide, 240)).toEqual({ zoom: 1, x: 0, y: 0 });
        expect(clampCrop({ zoom: 1, x: -999, y: 0 }, wide, 240).x).toBe(-240);
        expect(clampCrop({ zoom: 99, x: 0, y: 0 }, wide, 240).zoom).toBe(MAX_ZOOM);
    });

    it("zooms around the middle of the square", () => {
        const zoomed = zoomCrop(centeredCrop(wide, 240), 2, wide, 240);

        expect(zoomed).toEqual({ zoom: 2, x: -360, y: -120 });
        expectSquare(sourceSquare(zoomed, wide, 240), { x: 180, y: 60, size: 120 });
    });
});
