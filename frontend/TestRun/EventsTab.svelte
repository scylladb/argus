<script>
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import RawEvent from "./RawEvent.svelte";
    import StructuredEvent from "./StructuredEvent.svelte";
    import dayjs from "dayjs";
    import {sendMessage} from "../Stores/AlertStore";
    export let testRun;

    let parsedEvents = [];
    let filterString = "";
    let nemesisByKey = {};
    let nemesisPeriods = {};
    let eventEmbeddings = {};
    let isLoading = true;

    const displayCategories = {
        CRITICAL: {
            show: true,
            totalEvents: 0,
            eventsSubmitted: 0,
        },
        ERROR: {
            show: true,
            totalEvents: 0,
            eventsSubmitted: 0,
        },
        WARNING: {
            show: false,
            totalEvents: 0,
            eventsSubmitted: 0,
        },
        NORMAL: {
            show: false,
            totalEvents: 0,
            eventsSubmitted: 0,
        },
        DEBUG: {
            show: false,
            totalEvents: 0,
            eventsSubmitted: 0,
        },
    };

    /* OH GDO */
    const eventRegex = /(?<eventTimestamp>\d{2,4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})( <(?<receiveTimestamp>\d{2,4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})>)?: \((?<eventType>\w+) Severity\.(?<severity>[A-Z]+)\) (?<rawFields>.+)\n?/s;

    /**
     * @param {string} rawFields
     */
    const parseEventFields = function (rawFields) {
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
        }, {});

        return parsed;
    };

    /**
     * @param {string} event
     */
    const parseEvent = function (event) {
        let eventMetaIndex = event.match(/\n/)?.index;
        const eventMeta = event.slice(0, eventMetaIndex);
        const logLine = event.slice(eventMetaIndex);
        const match = eventRegex.exec(eventMeta);
        if (!match) throw new Error("Unable to parse the event");
        let parsedEvent = Object.assign({}, match.groups);
        let parsedFields = parseEventFields(parsedEvent.rawFields.trim());

        parsedEvent.fields = parsedFields;
        parsedEvent.logLine = logLine.trim();
        parsedEvent.time = new Date(Date.parse((parsedEvent?.eventTimestamp ?? "1970-01-01") + " UTC"));
        parsedEvent.parsed = true;
        parsedEvent.eventText = event;

        return parsedEvent;
    };


    const calculateNemesisKey = function(nemesis) {
        return `${nemesis.name}-${nemesis.start_time}-${nemesis.end_time}-${nemesis.target_node.name}`;
    };

    const defineNemesisPeriods = function(nemesisData) {
        let periods = nemesisData.reduce((acc, nemesis) => {
            acc[calculateNemesisKey(nemesis)] = {
                start: dayjs.utc(nemesis.start_time * 1000).toDate(),
                end: dayjs.utc(nemesis.end_time * 1000).toDate(),
            };
            return acc;
        }, {});

        return periods;
    };

    /**
     * @param {{last_events: string[], event_amount: int, severity: string }[]} events
     */
    const prepareEvents = function (events) {
        let flatEvents = events.reduce((acc, val) => {
            let eventIndex = 0; // Track the global event index

            displayCategories[val.severity].totalEvents = val.event_amount;
            displayCategories[val.severity].eventsSubmitted = val.last_events.length;

            // Map each event to include its index and any similar events
            const mappedEvents = val.last_events.map((event, idx) => ({
                text: event,
                severity: val.severity,
                index: idx,
                similars:
                    val.severity === "ERROR" || val.severity === "CRITICAL"
                        ? eventEmbeddings[`${val.severity}_${idx}`] ?? []
                        : [],
            }));
            eventIndex++;
            return [...acc, ...mappedEvents];
        }, []);

        let parsedEvents = flatEvents.map((val) => {
            let parsed = {};
            try {
                parsed = parseEvent(val.text);
                parsed.nemesis = Object.entries(nemesisPeriods)
                    .filter(([_, period]) => period.start <= parsed.time && period.end >= parsed.time)
                    .map(([key, _]) => nemesisByKey[key]);
                parsed.severity = val.severity;
                parsed.similars = val.similars;
            } catch (error) {
                parsed = {
                    time: new Date(0),
                    parsed: false,
                    text: val.text,
                    error: error.message,
                    severity: val.severity,
                    similars: val.similars,
                };
            }
            return parsed;
        });

        return parsedEvents.sort((a, b) => b.time - a.time);
    };

    onMount(async () => {
        isLoading = true;
        try {
            const response = await fetch(`/api/v1/client/sct/${testRun.id}/similar_events`);
            if (response.ok) {
                const data = await response.json();
                // Create a map of event index to similars set with severity prefix
                eventEmbeddings = data.response.reduce((acc, item) => {
                    acc[`${item.severity}_${item.event_index}`] = item.similars_set;
                    return acc;
                }, {});
            }
        } catch (error) {
            console.error("Failed to fetch event embeddings:", error);
            sendMessage("error", "Failed to fetch event embeddings", "StructuredEvent::toggleSimilars");
        }
        nemesisByKey = testRun.nemesis_data.reduce((acc, val) => {
            acc[calculateNemesisKey(val)] = val;
            return acc;
        }, {});
        nemesisPeriods = defineNemesisPeriods(testRun.nemesis_data);
        parsedEvents = prepareEvents(testRun?.events ?? []);
        isLoading = false;
    });
</script>

{#if parsedEvents.length > 0}
    <div class="p-2 event-container">
        <div class="d-flex justify-content-end mb-2 rounded bg-light p-1">
            {#each Object.entries(displayCategories) as [category, info]}
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <button
                    class="ms-2 px-2 py-1 btn severity-{category.toLowerCase()}"
                    on:click={() => (info.show = !info.show)}
                >
                    {#if info.show}
                        <Fa icon={faCheck} />
                    {:else}
                        <Fa icon={faTimes} />
                    {/if}
                    {category}
                    (<span class="pointer-help" title="Shown">{info.eventsSubmitted}</span> /
                    <span class="pointer-help" title="Happened during the test">{info.totalEvents}</span>)
                </button>
            {/each}
        </div>
        <div class="p-2">
            <input class="form-control" type="text" placeholder="Filter events" bind:value={filterString} />
        </div>
        {#each parsedEvents as event}
            {#if event.parsed}
                <StructuredEvent
                    bind:filterString
                    display={displayCategories[event.severity].show ?? true}
                    {event}
                    similars={event.similars}
                />
            {:else}
                <RawEvent eventText={event.text} errorMessage={event.error} />
            {/if}
        {/each}
    </div>
{:else if isLoading}
    <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center event-container">
        <span class="spinner-border me-4" /><span class="fs-4">Loading...</span>
    </div>
{:else}
    <div class="text-center p-1 text-muted">No events submitted yet.</div>
{/if}

<style>
    .pointer-help {
        cursor: help;
    }

    .event-container {
        max-height: 768px;
        overflow-y: scroll;
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
</style>
