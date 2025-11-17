<script module lang="ts">
    export interface SCTEvent {
        run_id: string;
        severity: string;
        ts: string;
        event_type: string;
        message: string;
        node?: string;
        received_timestamp?: string;
        nemesis_name?: string;
        duration?: number;
        target_node?: string;
        nemesis_status?: string;
        known_issue?: string;
    }

    export const SCTEventSeverity = {
        CRITICAL: "CRITICAL",
        ERROR: "ERROR",
        WARNING: "WARNING",
        NORMAL: "NORMAL",
        DEBUG: "DEBUG",
    }
    type SeverityValueType = typeof SCTEventSeverity[keyof typeof SCTEventSeverity];

    // svelte-ignore non_reactive_update
    enum TimelineEventType {
        Nemesis = "nemesis",
        Event = "event",
    }

    interface SCTEventApiResponse {
        status: string
        response: SCTEvent[]
    }

    export interface Options {
        subtype?: string
    }

    export class TimelineEvent {
        type: TimelineEventType
        event: NemesisInfo | SCTEvent
        ts: number
        tsEnd: number | null
        severity: string
        opts: Options | null
        id: string
        innerEvents: TimelineEvent[]

        constructor(type: TimelineEventType, event: SCTEvent | NemesisInfo, ts: number, severity: SeverityValueType, innerEvents: TimelineEvent[] | null = null, tsEnd: number | null = null, opts: Options | null = null) {
            this.type = type;
            this.event = event;
            this.ts = ts;
            this.severity = severity;
            this.opts = opts;
            this.tsEnd = tsEnd;
            this.innerEvents = innerEvents || [];
            this.id = `${this.type}-${this.severity}-${this.ts}`;
        }
    }

    export type EventSeverityFilter = Record<SeverityValueType, boolean>;
    type EventStore = Record<SeverityValueType, SCTEvent[]>;

</script>

<script lang="ts">
    import { onMount, onDestroy } from "svelte";

    import { sendMessage } from "../../Stores/AlertStore";
    import type { APIError, NemesisInfo, SCTTestRun } from "../TestRun.svelte";
    import SctEvent from "./SctEvent.svelte";
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import queryString from "query-string";
    import SctNemesis from "./SctNemesis.svelte";
    import { NemesisStatusBg, NemesisStatuses, TestStatus } from "../../Common/TestStatus";

    interface Props {
        testRun: SCTTestRun,
        nemeses: NemesisInfo[]
    }

    let { testRun, nemeses }: Props = $props();
    let events: EventStore = $state({});
    let refreshTimer: ReturnType<typeof setInterval> | undefined = $state();
    let eventCounters: Record<SeverityValueType, number> = $state(Object.fromEntries(Object.keys(SCTEventSeverity).map(s => [s, 0])));
    let severityFilter: EventSeverityFilter = $state({
        CRITICAL: true,
        ERROR: true,
        WARNING: false,
        NORMAL: false,
        DEBUG: false,
    });

    let nemesisFilter = $state({
        "started": false,
        "running": true,
        "failed": true,
        "skipped": false,
        "succeeded": false,
    });

    let eventFilterString = $state("");
    let nemesisFilterString = $state("");


    const countEventsBySeverity = async function (severity: SeverityValueType): Promise<SCTEvent[]> {
        try {
            const response = await fetch(`/api/v1/client/sct/${testRun.id}/events/${severity}/count`);
            const json: SCTEventApiResponse = await response.json();
            if (json.status !== "ok") {
                throw json;
            }
            return json.response;
        } catch (error) {
            if ((error as APIError)?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching events.\nMessage: ${(error as APIError).response.arguments[0]}`,
                    "SCTEvents::fetchEvents"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during events fetch",
                    "SCTEvents::fetchEvents"
                );
                console.log(error);
            }
        }
        return [];
    }

    const fetchEventsBySeverity = async function (severity: SeverityValueType, before: number | null = null, limit: number | null = null): Promise<SCTEvent[]> {
        try {
            const qs = queryString.stringify({
                limit: limit ? limit : eventCounters[severity],
                before: before,
            })
            const response = await fetch(`/api/v1/client/sct/${testRun.id}/events/${severity}/get?${qs}`);
            const json: SCTEventApiResponse = await response.json();
            if (json.status !== "ok") {
                throw json;
            }
            return json.response;
        } catch (error) {
            if ((error as APIError)?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching events.\nMessage: ${(error as APIError).response.arguments[0]}`,
                    "SCTEvents::fetchEvents"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during events fetch",
                    "SCTEvents::fetchEvents"
                );
                console.log(error);
            }
        }
        return [];
    }

    const updateCounters = function() {
        Object.keys(SCTEventSeverity).forEach(severity => eventCounters[severity] = events[severity].length)
    }

    const fetchEvents = async function (cursor = false, limit: number | null = null, fromCounters = false) {
        const entries = Object.entries(severityFilter);

        return (await Promise.all(entries.map(async ([severity, enabled]) => {
            const old = events[severity] || [];
            const localLimit = fromCounters ? Math.max(eventCounters[severity], 10000) : limit;
            const before = cursor && old.length > 0 ? Date.parse(old[0].ts) / 1000 : null;
            let val: [string, SCTEvent[]] = enabled ? [severity, await fetchEventsBySeverity(severity, before, localLimit)] : [severity, []];
            return val;
        }))).reduce((acc, [severity, events]) => {
            acc[severity] = events;
            return acc;
        }, {} as EventStore);
    }

    const handleSeverityClick = async function(severity: SeverityValueType) {
        severityFilter[severity] = !severityFilter[severity];
        events = await fetchEvents(false, null, true);
    }


    const handleNemesisFilterClick = async function(filter: string) {
        nemesisFilter[filter as keyof typeof nemesisFilter] = !nemesisFilter[filter as keyof typeof nemesisFilter];
    }


    const createTimeline = function(nemeses: NemesisInfo[], events: EventStore) {
        let sctEvents = Object
            .entries(events)
            .flatMap(([severity, events]) => events.map((event) => {return {severity, event}}))
            .map(({severity, event}) => new TimelineEvent(TimelineEventType.Event, event, Date.parse(event.ts), severity));

        let consumedEvents: TimelineEvent[] = [];

        let nemesisEvents = nemeses
            .map((nem, idx, src) => {
                let nextTs = src[idx + 1]?.end_time || Date.parse(testRun.end_time) || nem.start_time;
                const evt = new TimelineEvent(TimelineEventType.Nemesis, nem, nem.start_time * 1000, "nemesis", null, (nextTs || 0) * 1000, {subtype: "start"});
                let nemesisEvents = sctEvents.filter((event) => evt.ts <= event.ts && event.ts < (evt.tsEnd || evt.ts));
                evt.innerEvents = nemesisEvents;
                consumedEvents = [...consumedEvents, ...nemesisEvents];
                return evt;
            });
        let usedEventIds = consumedEvents.map(v => v.id);
        let remainder = sctEvents.filter((event) => !usedEventIds.includes(event.id));
        let timeline = [...nemesisEvents, ...remainder].sort((l, r) => l.ts - r.ts);
        return timeline;
    }

    let timeline: TimelineEvent[] = $derived(createTimeline(nemeses, events));

    onMount(async () => {
        events = await fetchEvents(false, 10000);
        updateCounters();
        refreshTimer = setInterval(async () => {
            if ([TestStatus.ABORTED, TestStatus.PASSED, TestStatus.FAILED, TestStatus.TEST_ERROR].includes(testRun.status)) {
                clearInterval(refreshTimer);
                refreshTimer = undefined;
                return;
            }
            events = await fetchEvents(false, null, true);
        }, 60 * 1000);
    });

    onDestroy(() => {
        if (refreshTimer) clearInterval(refreshTimer);
    })
</script>


<div class="p-2">
    <div>
        <div class="d-flex align-items-center mb-2">
            <div class="me-2 flex-fill">
                <input class="form-control" type="text" placeholder="Filter events..." bind:value={eventFilterString} />
            </div>
            <div class="flex-fill">
                <input class="form-control" type="text" placeholder="Filter nemeses..." bind:value={nemesisFilterString} />
            </div>
        </div>
    </div>
    <div class="d-flex mb-2 justify-content-end align-items-center">
        {#each Object.values(SCTEventSeverity) as severity}
            <button class="btn me-2 severity-{severity.toLowerCase()}" onclick={() => handleSeverityClick(severity)}>
                <Fa icon={severityFilter[severity] ? faCheck : faTimes}/> {severity} <span>{eventCounters[severity]}</span> / <span>{#await countEventsBySeverity(severity)}
                    <span class="spinner-grow spinner-grow-sm"></span>
                {:then value}
                    {value}
                {/await}</span>
            </button>
        {/each}
    </div>
    <div class="d-flex mb-2 justify-content-end align-items-ccenter">
        {#each Object.values(NemesisStatuses) as nemesisStatus}
            <button class="btn me-2 text-light {NemesisStatusBg[nemesisStatus]}" onclick={() => handleNemesisFilterClick(nemesisStatus)}>
                <Fa icon={nemesisFilter[nemesisStatus as keyof typeof nemesisFilter] ? faCheck : faTimes}/> {nemesisStatus.toLocaleUpperCase()}
            </button>
        {/each}
    </div>
    <div class="p-2 bg-light-one rounded" style="max-height: 1024px; overflow-y: scroll">
        {#each timeline as event}
            {#if event.type == TimelineEventType.Event}
                {#if severityFilter[event.severity]}
                    <div class="mb-2">
                        <SctEvent event={(event.event as SCTEvent)} filterState={severityFilter} options={event.opts || {}} bind:filterString={eventFilterString}/>
                    </div>
                {/if}
            {:else if event.type == TimelineEventType.Nemesis}
                {#if event.innerEvents.filter((e) => [SCTEventSeverity.CRITICAL, SCTEventSeverity.ERROR].includes((e.event as SCTEvent).severity)).length > 0 || nemesisFilter[event.event.status]}
                    <div class="mb-2">
                        <SctNemesis event={(event.event as NemesisInfo)} filterState={severityFilter} innerEvents={event.innerEvents} options={event.opts || {}} bind:filterString={nemesisFilterString} bind:eventFilterString/>
                    </div>
                {/if}
            {/if}
        {/each}
    </div>
</div>

<style>
    .severity-warning {
        background-color: #ffd416;
        color: black;
    }
    .severity-normal {
        background-color: #2d98c2;
        color: white;
    }
    .severity-debug {
        background-color: #7e6262;
        color: white;
    }
    .severity-info {
        background-color: #777777;
        color: white;
    }
    .severity-error {
        background-color: #ff0000;
        color: white;
    }
    .severity-critical {
        background-color: #692121;
        color: white;
    }
</style>
