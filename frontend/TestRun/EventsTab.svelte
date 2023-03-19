<script>
    import { onMount } from "svelte";
    import RawEvent from "./RawEvent.svelte";
    import StructuredEvent from "./StructuredEvent.svelte";
    export let testRun;

    let parsedEvents = [];
    let filterString = "";

    const displayCategories = {
        CRITICAL: true,
        ERROR: true,
        WARNING: false,
        NORMAL: false,
        DEBUG: false,
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
        parsedEvent.time = new Date(Date.parse(parsedEvent?.eventTimestamp ?? "1970-01-01" + " UTC"));
        parsedEvent.parsed = true;
        parsedEvent.eventText = event;

        return parsedEvent;
    };

    /**
     * @param {{last_events: string[]}[]} events
     */
    const prepareEvents = function (events) {
        let flatEvents = events.reduce((acc, val) => {
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

        return parsedEvents.sort((a, b) => b.time - a.time);
    };

    onMount(() => {
        parsedEvents = prepareEvents(testRun?.events ?? []);
    });
</script>

{#if parsedEvents.length > 0}
    <div class="p-2 event-container">
        <div class="d-flex justify-content-end mb-2 rounded bg-light p-1">
            {#each Object.keys(displayCategories) as category}
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <div class="ms-2 p-1 rounded border severity-{category.toLowerCase()}">
                    <input class="form-check-input me-1" type="checkbox" bind:checked={displayCategories[category]}>
                    <label class="form-check-label">{category}</label>
                </div>
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
                <StructuredEvent bind:filterString={filterString} display={displayCategories[event.severity] ?? true} {event} />
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

    .event-container {
        max-height: 768px;
        overflow-y: scroll;
    }

    .severity-warning {
        background-color: #ffc830;
    }
    .severity-normal {
        background-color: #33b4e7;
    }
    .severity-debug {
        background-color: #7e6262;
    }
    .severity-info {
        background-color: #bdbdbd;
    }
    .severity-error {
        background-color: #e91f1f;
    }
    .severity-critical {
        background-color: #ff033a;
    }
</style>
