<script lang="ts">
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../../Common/DateUtils";
    import type { EventSeverityFilter, Options, SCTEvent } from "./SctEvents.svelte";
    import { faNode } from "@fortawesome/free-brands-svg-icons";
    import Fa from "svelte-fa";
    import { faClipboard, faClock, faCopy, faServer, faSpider } from "@fortawesome/free-solid-svg-icons";

    interface Props {
        event: SCTEvent,
        filterState: EventSeverityFilter,
        options: Options,
        filterString: string,
    }
    let { event, filterState, options, filterString = $bindable() }: Props = $props();
    const MESSAGE_CUTOFF = 600;
    const SHORT_MESSAGE_LEN = 500;

    const sliceMessage = function (message: string): string {
        return fullMessage && message.length <= MESSAGE_CUTOFF ? message : message.slice(0, SHORT_MESSAGE_LEN);
    }

    const messageRegex = /\((?<eventType>\w+) Severity\.(?<severity>[A-Z]+)\) (?<rawFields>.+)\n?/s;
    const parseEventFields = function (rawFields: string) {
        let pos = 0;
        let currentChar;
        let splitPoints = [pos];
        let potentialSplit = false;
        let potentialSplitPos = 0;
        while (currentChar = rawFields.at(pos++)) { // eslint-disable-line
            if (currentChar == " ") {
                potentialSplit = true;
                potentialSplitPos = pos;
            } else if (potentialSplit && currentChar == "=") {
                splitPoints.push(potentialSplitPos);
                potentialSplit = false;
                potentialSplitPos = -1;
            }
        }

        let parsed = splitPoints.reduce((acc, value, idx, src) => {
            let field = rawFields.slice(value, src[idx + 1]);
            let [fieldKey, fieldVal] = field.split("=", 2);
            if (!fieldKey || !fieldVal) return acc;
            acc[fieldKey.trim()] = fieldVal.trim().replace(/[:,]$/, "");
            return acc;
        }, {} as ParsedFields);

        return parsed;
    };

    const parseEventMessage = function (message: string) {
        let eventMetaIndex = message.match(/\n/)?.index;
        const eventMeta = message.slice(0, eventMetaIndex);
        const logLine = message.slice(eventMetaIndex);
        const match = messageRegex.exec(eventMeta);
        if (!match) throw new Error("Unable to parse the event");
        let parsedMessage = Object.assign({}, match.groups as unknown) as ParsedMessage;
        let parsedFields = parseEventFields(parsedMessage.rawFields.trim());

        parsedMessage.fields = parsedFields;
        parsedMessage.logLine = logLine.trim();
        parsedMessage.parsed = true;
        parsedMessage.message = message;

        return parsedMessage;
    };

    let fullMessage = $state(false);
    let parsedMessage = $derived(parseEventMessage(event.message));

    const shouldFilter = function (filterString: string) {
        if (!filterString) return false;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((event.message.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

    type ParsedFields = Record<string, string>;

    interface ParsedMessage {
        fields: ParsedFields
        eventType: string,
        severity: string,
        rawFields: string,
        logLine: string,
        parsed: boolean,
        message: string
    }


</script>

{#if !shouldFilter(filterString)}
    <div class="ms-3 rounded overflow-hidden shadow-sm severity-border-{event.severity.toLowerCase()}">
        <div class="border-bottom bg-titlebar text-light p-1">
            <div class="d-flex mb-1">
                <div class="rounded bg-dark p-1">{event.event_type}</div>
                <div class="ms-2 p-1 bg-light text-dark rounded">{parsedMessage.fields["period_type"]}</div>
                <div class="ms-auto"></div>
                {#if event.duration}
                    <div class="ms-1 p-1 rounded bg-dark text-light">{humanizeDuration(event.duration * 1000, { round: true, largest: 2})}</div>
                {/if}
                <div class="ms-2 p-1 bg-light text-dark rounded">{timestampToISODate(event.ts, true)}</div>
                <button class="ms-2 btn btn-sm btn-success" onclick={() => navigator.clipboard.writeText(event.message)}><Fa icon={faCopy}/></button>
            </div>
            <div class="d-flex flex-wrap">
                {#if event.nemesis_name}
                    <div class="ms-2 rounded p-1 bg-light text-dark">
                        <Fa icon={faSpider}/> {event.nemesis_name}
                    </div>
                {/if}
                {#if event.known_issue}
                    <div class="ms-2 rounded p-1 bg-light text-dark">
                        <Fa icon={faClipboard}/> {event.known_issue}
                    </div>
                {/if}
                {#if event.nemesis_status}
                    <div class="ms-2 rounded p-1 bg-light text-dark">
                        {event.nemesis_status}
                    </div>
                {/if}
                {#if event.received_timestamp}
                    <div class="ms-2 rounded p-1 bg-warning text-dark">
                        <Fa icon={faClock}/> {event.received_timestamp}
                    </div>
                {/if}
                {#if event.target_node}
                    <div class="ms-2 rounded p-1 bg-light text-dark text-truncate" style="max-width: 256px">
                        <Fa icon={faServer}/>  {event.target_node}
                    </div>
                {/if}
                {#if event.node}
                    <div class="ms-2 rounded p-1 bg-light text-dark text-truncate" style="max-width: 256px">
                        <Fa icon={faServer}/> {event.node}
                    </div>
                {/if}
            </div>
        </div>
        <div class="bg-body p-2">
            <pre class="font-monospace p-2 rounded m-1 bg-light-two" style="white-space: pre-wrap !important">{sliceMessage(event.message)} {#if event.message.length > 500}<button class="btn btn-sm btn-light" onclick={() => fullMessage = !fullMessage}>...</button>{/if}</pre>
        </div>
    </div>
{/if}


<style>
    .bg-titlebar {
        background-color: #dddddd;
    }

    .bg-body {
        background-color: #ececec;
    }

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


    .severity-border-warning {
        border-left: 5px solid !important;
        border-color: #ffd416 !important;
        color: black;
    }
    .severity-border-normal {
        border-left: 5px solid !important;
        border-color: #2d98c2 !important;
    }
    .severity-border-debug {
        border-left: 5px solid !important;
        border-color: #7e6262 !important;
    }
    .severity-border-info {
        border-left: 5px solid !important;
        border-color: #777777 !important;
    }
    .severity-border-error {
        border-left: 5px solid !important;
        border-color: #ff0000 !important;
    }
    .severity-border-critical {
        border-left: 5px solid !important;
        border-color: #692121 !important;
    }
</style>
