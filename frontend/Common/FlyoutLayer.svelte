<script lang="ts">
    import Fa from "svelte-fa";
    import { faPlus } from "@fortawesome/free-solid-svg-icons";
    import { flyAlongArc, ping, type Flight, type Point } from "./flyout";

    interface Props {
        flights: Flight[];
        onLanded: (id: number) => void;
    }

    let { flights, onLanded }: Props = $props();

    let pings: { id: number; at: Point }[] = $state([]);

    const land = (flight: Flight) => {
        pings.push({ id: flight.id, at: flight.to });
        onLanded(flight.id);
    };

    const removePing = (id: number) => {
        pings = pings.filter((entry) => entry.id !== id);
    };
</script>

<div class="flyout-layer" aria-hidden="true">
    {#each flights as flight (flight.id)}
        <div
            class="flyout-anchor"
            style="transform: translate({flight.from.x}px, {flight.from.y}px)"
            use:flyAlongArc={{ flight, onLanded: () => land(flight) }}
        >
            <span class="flyout-chip badge rounded-pill text-bg-primary shadow">
                <Fa icon={faPlus} size="xs" />
                {flight.label}
            </span>
        </div>
    {/each}
    {#each pings as entry (entry.id)}
        <div class="flyout-anchor" use:ping={{ at: entry.at, onDone: () => removePing(entry.id) }}>
            <span class="flyout-ping"></span>
        </div>
    {/each}
</div>

<style>
    .flyout-layer {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 1080;
        overflow: hidden;
    }

    .flyout-anchor {
        position: absolute;
        left: 0;
        top: 0;
        transform-origin: 0 0;
        will-change: transform;
    }

    .flyout-chip {
        display: inline-block;
        transform: translate(-50%, -50%);
        max-width: 14rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .flyout-ping {
        display: block;
        width: 1.5rem;
        height: 1.5rem;
        transform: translate(-50%, -50%);
        border-radius: 50%;
        border: 3px solid var(--bs-primary);
        background-color: transparent;
    }
</style>
