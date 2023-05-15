<script>
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import RawEvent from "./RawEvent.svelte";
    import StructuredEvent from "./StructuredEvent.svelte";
    export let testRun;

    let parsedEvents = [];
    let filterString = "";

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

    /**
     * @param {{last_events: string[], event_amount: int, severity: string }[]} events
     */
    const prepareEvents = function (events, nemesisData) {
        let flatEvents = events.reduce((acc, val) => {
            displayCategories[val.severity].totalEvents = val.event_amount;
            displayCategories[val.severity].eventsSubmitted = val.last_events.length;
            return [...acc, ...val.last_events];
        }, []);

        let parsedEvents = flatEvents.map((val) => {
            let parsed = {};
            try {
                parsed = parseEvent(val);
            } catch (error) {
                parsed = {
                    time: new Date(0),
                    parsed: false,
                    text: val,
                    error: error.message
                };
            }
            return parsed;
        });

        let sortedNemesises = nemesisData.sort((a, b) => a.start_time - b.start_time);
        let nemesisIndex = 0;
        for (let event of parsedEvents.sort((a, b) => a.time - b.time)) {
            event.nemesis = undefined;
            while(sortedNemesises[nemesisIndex]) {
                if (event.time.getTime() < sortedNemesises[nemesisIndex].start_time * 1000) {
                    break;
                } else if(event.time.getTime() <= sortedNemesises[nemesisIndex].end_time * 1000) {
                    event.nemesis = sortedNemesises[nemesisIndex];
                    break;
                }
                nemesisIndex++;
            }

        }

        return parsedEvents.sort((a, b) => b.time - a.time);
    };

    onMount(() => {
        parsedEvents = prepareEvents(testRun?.events ?? [], testRun?.nemesis_data ?? []);
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
                        <Fa icon={faCheck}/>
                    {:else}
                        <Fa icon={faTimes}/>
                    {/if}
                    {category}
                    (<span class="pointer-help" title="Shown">{info.eventsSubmitted}</span> / <span class="pointer-help" title="Happened during the test">{info.totalEvents}</span>)
                </button>
            {/each}
        </div>
        <div class="p-2">
            <input
                class="form-control"
                type="text"
                placeholder="Filter events"
                bind:value={filterString}
            />
        </div>
        {#each parsedEvents as event}
            {#if event.parsed}
                <StructuredEvent bind:filterString={filterString} display={displayCategories[event.severity].show ?? true} {event} />
            {:else}
                <RawEvent eventText={event.text} errorMessage={event.error} />
            {/if}
        {/each}
    </div>
{:else}
    <div class="text-center p-1 text-muted">
            No events submitted yet.
    </div>
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
