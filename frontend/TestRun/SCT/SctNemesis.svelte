<script lang="ts">
    import Fa from "svelte-fa";
    import type { NemesisInfo } from "../TestRun.svelte";
    import { SCTEventSeverity, type EventSeverityFilter, type Options, type SCTEvent, type TimelineEvent } from "./SctEvents.svelte";
    import { faArrowDown, faArrowUp, faServer, faSpider, faTimeline } from "@fortawesome/free-solid-svg-icons";
    import { NemesisStatusBg, NemesisStatusFg } from "../../Common/TestStatus";
    import { timestampToISODate } from "../../Common/DateUtils";
    import SctEvent from "./SctEvent.svelte";

    interface Props {
        event: NemesisInfo,
        filterState: EventSeverityFilter,
        options: Options,
        innerEvents: TimelineEvent[],
        filterString: string,
        eventFilterString: string,
    }
    let { event, filterState, innerEvents, options, filterString = $bindable(), eventFilterString = $bindable()}: Props = $props();

    let hasErrors = $derived(innerEvents.filter((evt: TimelineEvent) => [SCTEventSeverity.CRITICAL, SCTEventSeverity.ERROR].includes((evt.event as SCTEvent).severity)).length > 0);
    let expandEvents = $derived(hasErrors);
    let showTrace = $state(false);

    const shouldFilter = function (filterString: string) {
        if (!filterString) return false;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((event.name.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

</script>

{#if !shouldFilter(filterString)}
    <div class="overflow-hidden border p-1 shadow-sm rounded bg-white">
        <div class="d-flex align-items-center">
            <div>
                <Fa icon={faSpider} /> <span class="fw-bold">{event.name}</span>
            </div>
            <div class="ms-auto rounded bg-light text-dark">
                {timestampToISODate(event.end_time * 1000, true)}
            </div>
            <div class="ms-2 px-1 rounded {NemesisStatusBg[event.status as keyof typeof NemesisStatusBg]} {NemesisStatusFg[event.status as keyof typeof NemesisStatusFg]}">
                {event.status.toLocaleUpperCase()}
            </div>
            {#if innerEvents.length > 0}
                <div class="ms-2"><button class="btn btn-sm btn-primary" onclick={() => (expandEvents = !expandEvents)}><Fa icon={expandEvents ? faArrowUp : faArrowDown} /></button></div>
            {/if}
        </div>
        <div class="d-flex align-items-center mb-1">
            <div class="rounded px-1 bg-light text-dark">
                <Fa icon={faServer}/> {event.target_node.name} ({event.target_node.ip})
            </div>
        </div>
        {#if event.stack_trace}
            <div>
                <pre class="font-monospace p-2 rounded m-1 bg-light-two" style="white-space: pre-wrap">{event.stack_trace}</pre>
            </div>
        {/if}
        {#if innerEvents.length > 0}
            <div class="rounded shadow bg-light-one p-2 collapse" class:show={expandEvents}>
                {#each innerEvents as event}
                    <div class="mb-2">
                        <SctEvent event={(event.event as SCTEvent)} filterState={filterState} options={event.opts || {}} bind:filterString={eventFilterString}/>
                    </div>
                {/each}
            </div>
        {/if}
    </div>
{/if}


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
