export const VIEWPORT = 240;
export const OUTPUT = 256;
export const MAX_ZOOM = 4;

export interface Crop {
    zoom: number;
    x: number;
    y: number;
}

export interface Size {
    width: number;
    height: number;
}

export const coverScale = (image: Size, view = VIEWPORT): number =>
    Math.max(view / image.width, view / image.height);

export const clampCrop = (crop: Crop, image: Size, view = VIEWPORT): Crop => {
    const zoom = Math.min(MAX_ZOOM, Math.max(1, crop.zoom));
    const scale = coverScale(image, view) * zoom;
    return {
        zoom,
        x: Math.min(0, Math.max(view - image.width * scale, crop.x)),
        y: Math.min(0, Math.max(view - image.height * scale, crop.y)),
    };
};

export const centeredCrop = (image: Size, view = VIEWPORT): Crop => {
    const scale = coverScale(image, view);
    return { zoom: 1, x: (view - image.width * scale) / 2, y: (view - image.height * scale) / 2 };
};

export const zoomCrop = (crop: Crop, zoom: number, image: Size, view = VIEWPORT): Crop => {
    const before = coverScale(image, view) * crop.zoom;
    const after = coverScale(image, view) * Math.min(MAX_ZOOM, Math.max(1, zoom));
    const centerX = (view / 2 - crop.x) / before;
    const centerY = (view / 2 - crop.y) / before;
    return clampCrop({ zoom, x: view / 2 - centerX * after, y: view / 2 - centerY * after }, image, view);
};

export const sourceSquare = (crop: Crop, image: Size, view = VIEWPORT) => {
    const scale = coverScale(image, view) * crop.zoom;
    return { x: -crop.x / scale, y: -crop.y / scale, size: view / scale };
};
