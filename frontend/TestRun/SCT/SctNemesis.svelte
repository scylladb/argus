<script lang="ts">
    import Fa from "svelte-fa";
    import type { NemesisInfo } from "../TestRun.svelte";
    import type { EventSeverityFilter, Options } from "./SctEvents.svelte";
    import { faArrowDown, faArrowRight, faArrowUp, faFlagCheckered, faGun } from "@fortawesome/free-solid-svg-icons";
    import { NemesisStatusBg, NemesisStatusFg } from "../../Common/TestStatus";
    import { timestampToISODate } from "../../Common/DateUtils";

    interface Props {
        event: NemesisInfo,
        filterState: EventSeverityFilter,
        options: Options,
    }
    let { event, filterState, options }: Props = $props();
    let showTrace = $state(false);
</script>

<div class="overflow-hidden">
    <div class="d-flex align-items-center">
        <div class="ms-2">
            <Fa icon={ options.subtype == "end" ? faFlagCheckered : faArrowRight } /> <span class="fw-bold">{event.name}</span> has {options.subtype == "end" ? "ended" : "started"} on node <span class="fw-bold">{event.target_node.name} ({event.target_node.ip})</span>.
        </div>
        {#if options.subtype == "end"}
            <div class="ms-auto"></div>
            <div class="ms-2 rounded bg-light text-dark">
                {timestampToISODate(event.end_time * 1000, true)}
            </div>
            <div class="ms-2 rounded {NemesisStatusBg[event.status as keyof typeof NemesisStatusBg]} {NemesisStatusFg[event.status as keyof typeof NemesisStatusFg]}">
                {event.status.toLocaleUpperCase()}
            </div>
            {#if event.stack_trace}
                <div class="ms-2"><button class="btn btn-sm btn-primary" onclick={() => (showTrace = !showTrace)}><Fa icon={showTrace ? faArrowUp : faArrowDown} /></button></div>
            {/if}
        {:else}
            <div class="ms-auto"></div>
            <div class="ms-2 rounded bg-light text-dark">
                {timestampToISODate(event.start_time * 1000, true)}
            </div>
        {/if}
    </div>
    {#if options.subtype == "end"}
        <div class:d-none={!showTrace}>
            <pre class="font-monospace p-2 rounded m-1 bg-light-two" style="white-space: pre-wrap">{event.stack_trace}</pre>
        </div>
    {/if}
</div>


<style>
    .border-start {
        border-left: 5px solid !important;
        border-color: #000000 !important;
    }

    .border-end {
        border-left: 5px dashed !important;
        border-color: #000000 !important;
    }
</style>
