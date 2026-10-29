<script lang="ts">
    import Fa from "svelte-fa";
    import {
        faArrowUpRightFromSquare,
        faChevronLeft,
        faChevronRight,
        faCompress,
        faExpand,
        faMagnifyingGlassMinus,
        faMagnifyingGlassPlus,
        faXmark,
    } from "@fortawesome/free-solid-svg-icons";
    import { FIT, measure, zoomAt, zoomPan, type View } from "./zoomPan";

    interface Props {
        selectedScreenshot: string;
        screenshots?: string[];
    }

    let { selectedScreenshot = $bindable(), screenshots = [] }: Props = $props();

    const ZOOM_STEP = 1.25;

    let view = $state.raw<View>(FIT);
    let failed = $state(false);
    let stage = $state<HTMLDivElement>();
    let image = $state<HTMLImageElement>();

    const index = $derived(screenshots.indexOf(selectedScreenshot));
    const multiple = $derived(index >= 0 && screenshots.length > 1);
    const hasPrev = $derived(multiple && index > 0);
    const hasNext = $derived(multiple && index < screenshots.length - 1);

    function show(url: string) {
        selectedScreenshot = url;
        view = FIT;
        failed = false;
    }

    function close() {
        show("");
    }

    function step(delta: number) {
        const target = multiple ? screenshots[index + delta] : undefined;
        if (target) {
            show(target);
        }
    }

    function zoomBy(factor: number) {
        if (stage && image) {
            view = zoomAt(view, factor, { x: 0, y: 0 }, measure(stage, image));
        }
    }

    function fit() {
        view = FIT;
    }

    function actual() {
        if (stage && image) {
            const bounds = measure(stage, image);
            const scale = bounds.imageWidth > 0 ? image.naturalWidth / bounds.imageWidth : 1;
            view = zoomAt(FIT, scale, { x: 0, y: 0 }, bounds);
        }
    }

    const keys: Record<string, () => void> = {
        Escape: close,
        ArrowLeft: () => step(-1),
        ArrowRight: () => step(1),
        "+": () => zoomBy(ZOOM_STEP),
        "=": () => zoomBy(ZOOM_STEP),
        "-": () => zoomBy(1 / ZOOM_STEP),
        "0": fit,
        "1": actual,
    };

    function handleKeyDown(event: KeyboardEvent) {
        if (event.altKey || event.ctrlKey || event.metaKey) {
            return;
        }
        const action = selectedScreenshot ? keys[event.key] : undefined;
        if (action) {
            event.preventDefault();
            action();
        }
    }

    function dialogOpen(node: HTMLElement) {
        const trigger = document.activeElement;
        document.body.classList.add("overflow-hidden");
        node.focus();
        return {
            destroy() {
                document.body.classList.remove("overflow-hidden");
                if (trigger instanceof HTMLElement && trigger.isConnected) {
                    trigger.focus();
                }
            },
        };
    }
</script>

<svelte:window onkeydown={handleKeyDown} />
{#if selectedScreenshot}
    <div
        class="screenshot-viewer position-fixed top-0 start-0 w-100 h-100 d-flex flex-column"
        role="dialog"
        aria-modal="true"
        aria-label="Screenshot viewer"
        tabindex="-1"
        use:dialogOpen
    >
        <div class="d-flex align-items-center gap-2 px-3 py-1 text-light">
            {#if multiple}
                <span>{index + 1} / {screenshots.length}</span>
            {/if}
            <div class="ms-auto d-flex align-items-center gap-1">
                <button
                    type="button"
                    class="btn btn-link text-light fs-5"
                    title="Zoom out"
                    aria-label="Zoom out"
                    onclick={() => zoomBy(1 / ZOOM_STEP)}
                >
                    <Fa icon={faMagnifyingGlassMinus} />
                </button>
                <button
                    type="button"
                    class="btn btn-link text-light fs-5"
                    title="Zoom in"
                    aria-label="Zoom in"
                    onclick={() => zoomBy(ZOOM_STEP)}
                >
                    <Fa icon={faMagnifyingGlassPlus} />
                </button>
                <button type="button" class="btn btn-link text-light fs-5" title="Fit to window" aria-label="Fit to window" onclick={fit}>
                    <Fa icon={faCompress} />
                </button>
                <button type="button" class="btn btn-link text-light fs-5" title="Actual pixels" aria-label="Actual pixels" onclick={actual}>
                    <Fa icon={faExpand} />
                </button>
                <a
                    class="btn btn-link text-light fs-5"
                    href={selectedScreenshot}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open original"
                    aria-label="Open original"
                >
                    <Fa icon={faArrowUpRightFromSquare} />
                </a>
                <button type="button" class="btn btn-link text-light fs-4" title="Close" aria-label="Close" onclick={close}>
                    <Fa icon={faXmark} />
                </button>
            </div>
        </div>
        <div
            class="screenshot-stage flex-grow-1 position-relative"
            class:zoomed={view.scale > 1}
            bind:this={stage}
            use:zoomPan={{
                view: () => view,
                setView: (next) => (view = next),
                image: () => image,
                onTap: close,
                onSwipe: (direction) => step(direction === "next" ? 1 : -1),
            }}
        >
            {#if failed}
                <div class="position-absolute top-50 start-50 translate-middle text-center text-light">
                    <p>The screenshot could not be loaded.</p>
                    <a class="link-light" href={selectedScreenshot} target="_blank" rel="noopener noreferrer">Open the original</a>
                </div>
            {:else}
                <img
                    bind:this={image}
                    src={selectedScreenshot}
                    alt="Screenshot"
                    draggable="false"
                    style="transform: translate({view.x}px, {view.y}px) scale({view.scale})"
                    onerror={() => (failed = true)}
                />
            {/if}
            {#if multiple}
                <button
                    type="button"
                    class="btn btn-link text-light fs-2 position-absolute top-50 start-0 translate-middle-y"
                    title="Previous screenshot"
                    aria-label="Previous screenshot"
                    disabled={!hasPrev}
                    onclick={() => step(-1)}
                >
                    <Fa icon={faChevronLeft} />
                </button>
                <button
                    type="button"
                    class="btn btn-link text-light fs-2 position-absolute top-50 end-0 translate-middle-y"
                    title="Next screenshot"
                    aria-label="Next screenshot"
                    disabled={!hasNext}
                    onclick={() => step(1)}
                >
                    <Fa icon={faChevronRight} />
                </button>
            {/if}
        </div>
    </div>
{/if}

<style>
    .screenshot-viewer {
        background-color: rgba(0, 0, 0, 0.85);
        z-index: 9999;
    }

    .screenshot-stage {
        min-height: 0;
        overflow: hidden;
        touch-action: none;
        user-select: none;
        overscroll-behavior: contain;
    }

    .screenshot-stage img {
        position: absolute;
        inset: 0;
        margin: auto;
        max-width: 100%;
        max-height: 100%;
        transform-origin: center;
    }

    .screenshot-stage.zoomed {
        cursor: grab;
    }

    .screenshot-stage.zoomed:active {
        cursor: grabbing;
    }
</style>
