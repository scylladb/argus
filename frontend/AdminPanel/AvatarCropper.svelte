<script lang="ts">
    import { MAX_ZOOM, OUTPUT, VIEWPORT, centeredCrop, clampCrop, coverScale, sourceSquare, zoomCrop, type Crop,
             type Size } from "./avatarCrop";

    interface Props {
        file: File;
    }

    let { file }: Props = $props();

    const KEY_STEP = 10;
    const ZOOM_STEP = 0.1;

    let image = $state<HTMLImageElement>();
    let natural = $state<Size | null>(null);
    let crop = $state<Crop>({ zoom: 1, x: 0, y: 0 });
    let drag: { pointer: number; x: number; y: number; crop: Crop } | null = null;

    const url = $derived(URL.createObjectURL(file));
    const scale = $derived(natural ? coverScale(natural) * crop.zoom : 1);

    $effect(() => {
        const current = url;
        natural = null;
        return () => URL.revokeObjectURL(current);
    });

    const loaded = () => {
        if (!image) return;
        natural = { width: image.naturalWidth, height: image.naturalHeight };
        crop = centeredCrop(natural);
    };

    const move = (x: number, y: number) => {
        if (natural) crop = clampCrop({ ...crop, x, y }, natural);
    };

    const zoomTo = (zoom: number) => {
        if (natural) crop = zoomCrop(crop, zoom, natural);
    };

    const pointerDown = (event: PointerEvent) => {
        drag = { pointer: event.pointerId, x: event.clientX, y: event.clientY, crop: { ...crop } };
        (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    };

    const pointerMove = (event: PointerEvent) => {
        if (drag?.pointer !== event.pointerId) return;
        move(drag.crop.x + event.clientX - drag.x, drag.crop.y + event.clientY - drag.y);
    };

    const wheel = (event: WheelEvent) => {
        event.preventDefault();
        zoomTo(crop.zoom - Math.sign(event.deltaY) * ZOOM_STEP);
    };

    const key = (event: KeyboardEvent) => {
        const moves: Record<string, [number, number]> = {
            ArrowLeft: [KEY_STEP, 0], ArrowRight: [-KEY_STEP, 0], ArrowUp: [0, KEY_STEP], ArrowDown: [0, -KEY_STEP],
        };
        if (moves[event.key]) {
            move(crop.x + moves[event.key][0], crop.y + moves[event.key][1]);
        } else if (event.key === "+" || event.key === "=") {
            zoomTo(crop.zoom + ZOOM_STEP);
        } else if (event.key === "-") {
            zoomTo(crop.zoom - ZOOM_STEP);
        } else {
            return;
        }
        event.preventDefault();
    };

    export const toBlob = (): Promise<Blob> => {
        if (!image || !natural) return Promise.reject(new Error("The picture is still loading"));
        const canvas = document.createElement("canvas");
        canvas.width = OUTPUT;
        canvas.height = OUTPUT;
        const context = canvas.getContext("2d");
        if (!context) return Promise.reject(new Error("This browser cannot crop pictures"));
        const square = sourceSquare(crop, natural);
        context.imageSmoothingQuality = "high";
        context.drawImage(image, square.x, square.y, square.size, square.size, 0, 0, OUTPUT, OUTPUT);
        return new Promise((resolve, reject) =>
            canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The picture could not be cropped"))),
                          "image/png"));
    };
</script>

<div class="d-flex flex-column align-items-center gap-2">
    <div
        class="viewport rounded"
        style:width="{VIEWPORT}px"
        style:height="{VIEWPORT}px"
        role="application"
        tabindex="0"
        aria-label="Picture crop. Drag or use the arrow keys to move, the wheel or + and - to zoom."
        title="Drag to move, scroll to zoom"
        onpointerdown={pointerDown}
        onpointermove={pointerMove}
        onpointerup={() => (drag = null)}
        onpointercancel={() => (drag = null)}
        onwheel={wheel}
        onkeydown={key}
    >
        <img
            bind:this={image}
            src={url}
            alt=""
            draggable="false"
            class:invisible={!natural}
            style:width="{(natural?.width ?? 0) * scale}px"
            style:height="{(natural?.height ?? 0) * scale}px"
            style:transform="translate({crop.x}px, {crop.y}px)"
            onload={loaded}
        />
        <div class="circle" aria-hidden="true"></div>
    </div>
    <input
        type="range"
        class="form-range zoom"
        min="1"
        max={MAX_ZOOM}
        step="0.01"
        value={crop.zoom}
        aria-label="Zoom"
        title="Zoom"
        disabled={!natural}
        oninput={(event) => zoomTo(Number((event.currentTarget as HTMLInputElement).value))}
    />
</div>

<style>
    .viewport {
        position: relative;
        overflow: hidden;
        cursor: grab;
        touch-action: none;
        background: var(--bs-secondary-bg);
    }

    .viewport:active {
        cursor: grabbing;
    }

    .viewport img {
        position: absolute;
        top: 0;
        left: 0;
        max-width: none;
        user-select: none;
        pointer-events: none;
        transform-origin: 0 0;
    }

    .circle {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        box-shadow: 0 0 0 999px rgb(0 0 0 / 0.5);
        outline: 2px solid rgb(255 255 255 / 0.8);
        pointer-events: none;
    }

    .zoom {
        width: 240px;
    }
</style>
