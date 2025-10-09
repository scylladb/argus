<script lang="ts">
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import { onMount, tick } from "svelte";
    import Fa from "svelte-fa";
    import RawEvent from "./RawEvent.svelte";
    import StructuredEvent from "./StructuredEvent.svelte";
    import dayjs from "dayjs";
    import {sendMessage} from "../Stores/AlertStore";
    let { testRun } = $props();

    let parsedEvents = $state([]);
    let filterString = $state("");
    let nemesisByKey = {};
    let nemesisPeriods = {};
    let eventEmbeddings = {};
    let eventDuplicates = {};
    let distinctEvents = $state({ ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} });
    let duplicateParents = $state({ ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} });
    let shownDuplicates = $state({
        ERROR: new Set(),
        CRITICAL: new Set(),
        WARNING: new Set(),
        NORMAL: new Set(),
        DEBUG: new Set(),
    });
    let hasSimilarEventsData = $state(false);
    let isLoading = $state(true);
    let eventContainer: HTMLDivElement;

    const displayCategories = $state({
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
    });

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
     * Builds a map of distinct events and their duplicates for ERROR and CRITICAL severities.
     *
     * The concept of distinct events:
     * - Events with the same content are considered duplicates
     * - Only one "distinct" event is shown by default, representing all duplicates
     * - Each distinct event maintains a list of its duplicate event indices
     * - The backend provides a duplicates_list for each event containing indices of similar events
     *
     * Algorithm:
     * 1. For each event, check if it's already processed as a duplicate
     * 2. If not processed, check if any existing distinct event is in this event's duplicates list
     * 3. If found, add this event to the existing distinct event's duplicates
     * 4. If not found, create a new distinct event with its duplicates list
     *
     * @param {Array} eventData - Array of event objects with event_index, severity, and duplicates_list
     * @returns {{ distinct: Object, parentMap: Object }} Distinct lookup plus a reverse map for duplicates
     */
    const buildDistinctEvents = function(eventData) {
        const distinct = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };
        const parentMap = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };

        const processEventsForSeverity = (severity) => {
            const events = eventData.filter(event => event.severity === severity);
            events.forEach(event => {
                const eventIdx = event.event_index;
                const duplicatesList = event.duplicates_list || [];

                // Check if this event is already a duplicate of an existing distinct event
                let existingParent = null;
                for (const [distinctIdx, duplicates] of Object.entries(distinct[severity])) {
                    if (duplicates.includes(eventIdx)) {
                        existingParent = parseInt(distinctIdx);
                        break;
                    }
                }

                if (existingParent !== null) {
                    parentMap[severity][eventIdx] = existingParent;
                    return;
                }

                // Check if any existing distinct event is in this event's duplicates list
                let foundParent = null;
                for (const [distinctIdx, duplicates] of Object.entries(distinct[severity])) {
                    if (duplicatesList.includes(parseInt(distinctIdx))) {
                        foundParent = parseInt(distinctIdx);
                        break;
                    }
                }

                if (foundParent !== null) {
                    // Add this event to the existing distinct event's duplicates
                    distinct[severity][foundParent].push(eventIdx);
                    parentMap[severity][eventIdx] = foundParent;
                } else {
                    // Create new distinct event and map its duplicates back to it
                    distinct[severity][eventIdx] = duplicatesList.slice();
                    duplicatesList.forEach(idx => {
                        parentMap[severity][idx] = eventIdx;
                    });
                }
            });
        };

        processEventsForSeverity('ERROR');
        processEventsForSeverity('CRITICAL');

        return { distinct, parentMap };
    };

    /**
     * Returns the number of duplicates for a distinct event, or -1 if the event is itself a duplicate.
     *
     * For ERROR/CRITICAL events:
     *   - If similar events data is not available, return 0 (no duplicate filtering)
     *   - If the event is a distinct event (hasOwnProperty in distinctEvents), return its duplicates count
     *   - If the event is a duplicate (not a key in distinctEvents), return -1
     *   - For other severities, return 0
     */
    const getNumberOfDuplicates = function(event) {
        if (event.severity !== 'ERROR' && event.severity !== 'CRITICAL') {
            return 0;
        }
        if (!hasSimilarEventsData) {
            return 0;
        }
        if (!distinctEvents[event.severity].hasOwnProperty(event.index)) {
            // This is a duplicate event
            return -1;
        }
        const duplicates = distinctEvents[event.severity][event.index] || [];
        return duplicates.length;
    };

    // True when every duplicate for the event is currently expanded.
    const areDuplicatesVisible = function(event) {
        if (event.severity !== 'ERROR' && event.severity !== 'CRITICAL') {
            return false;
        }
        if (!hasSimilarEventsData) {
            return false;
        }
        if (!distinctEvents[event.severity].hasOwnProperty(event.index)) {
            return false;
        }
        const duplicateIndices = distinctEvents[event.severity][event.index] || [];
        if (!duplicateIndices.length) {
            return false;
        }
        return duplicateIndices.every(idx => shownDuplicates[event.severity].has(idx));
    };

    // True when any ERROR/CRITICAL event has duplicate entries available.
    const hasDuplicateEvents = function() {
        if (!hasSimilarEventsData) {
            return false;
        }
        return ['ERROR', 'CRITICAL'].some(severity =>
            Object.values(distinctEvents[severity] ?? {}).some(duplicates => duplicates.length > 0)
        );
    };

    // Checks whether the global view already has all duplicates visible.
    const allDuplicatesShown = function() {
        if (!hasDuplicateEvents()) {
            return false;
        }
        return ['ERROR', 'CRITICAL'].every(severity => {
            const duplicatesByEvent = Object.values(distinctEvents[severity] ?? {});
            for (const duplicates of duplicatesByEvent) {
                for (const idx of duplicates) {
                    if (!shownDuplicates[severity].has(idx)) {
                        return false;
                    }
                }
            }
            return true;
        });
    };

    /**
     * Toggles the visibility of duplicate events for a given distinct event.
     *
     * @param {Object} event - The distinct event object containing severity and index
     * @param {number} [anchorIndex] - Optional index used to keep the clicked entry in view
     */
    const toggleDuplicates = async function(event, anchorIndex = event.index) {
        if (event.severity !== 'ERROR' && event.severity !== 'CRITICAL') {
            return;
        }
        if (!hasSimilarEventsData) {
            return;
        }

        const anchorKey = `event-${event.severity}-${anchorIndex}`;
        let relativeOffset: number | null = null;

        if (eventContainer) {
            const target = eventContainer.querySelector<HTMLElement>(`[data-event-key="${anchorKey}"]`);
            if (target) {
                const containerScrollTop = eventContainer.scrollTop;
                relativeOffset = target.offsetTop - containerScrollTop;
            }
        }

        const duplicateIndices = distinctEvents[event.severity][event.index] || [];

        const newShownDuplicates = {
            ERROR: new Set(shownDuplicates.ERROR),
            CRITICAL: new Set(shownDuplicates.CRITICAL),
            WARNING: new Set(shownDuplicates.WARNING),
            NORMAL: new Set(shownDuplicates.NORMAL),
            DEBUG: new Set(shownDuplicates.DEBUG)
        };

        // Check if any duplicates are currently shown
        const anyDuplicatesShown = duplicateIndices.some(idx =>
            shownDuplicates[event.severity].has(idx)
        );

        if (anyDuplicatesShown) {
            // Hide all duplicates
            duplicateIndices.forEach(idx => {
                newShownDuplicates[event.severity].delete(idx);
            });
        } else {
            // Show all duplicates
            duplicateIndices.forEach(idx => {
                newShownDuplicates[event.severity].add(idx);
            });
        }

        shownDuplicates = newShownDuplicates;

        if (relativeOffset !== null && eventContainer) {
            await tick();
            const updatedTarget = eventContainer.querySelector<HTMLElement>(`[data-event-key="${anchorKey}"]`);
            if (updatedTarget) {
                eventContainer.scrollTop = Math.max(updatedTarget.offsetTop - relativeOffset, 0);
            }
        }
    };

    // Bulk apply duplicate visibility for ERROR/CRITICAL events.
    const setAllDuplicatesVisibility = function(showAll: boolean) {
        const newShownDuplicates = {
            ERROR: new Set(),
            CRITICAL: new Set(),
            WARNING: new Set(shownDuplicates.WARNING),
            NORMAL: new Set(shownDuplicates.NORMAL),
            DEBUG: new Set(shownDuplicates.DEBUG)
        };

        if (showAll) {
            ['ERROR', 'CRITICAL'].forEach(severity => {
                Object.values(distinctEvents[severity] ?? {}).forEach(duplicates => {
                    duplicates.forEach(idx => newShownDuplicates[severity].add(idx));
                });
            });
        }

        shownDuplicates = newShownDuplicates;
    };

    // Global toggle wired to toolbar button; preserves scroll position.
    const toggleAllDuplicates = async function() {
        if (!hasDuplicateEvents()) {
            return;
        }
        const preservedScroll = eventContainer ? eventContainer.scrollTop : null;
        const shouldHide = allDuplicatesShown();
        setAllDuplicatesVisibility(!shouldHide);
        if (preservedScroll !== null && eventContainer) {
            await tick();
            eventContainer.scrollTop = preservedScroll;
        }
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
                duplicates:
                    val.severity === "ERROR" || val.severity === "CRITICAL"
                        ? eventDuplicates[`${val.severity}_${idx}`] ?? []
                        : [],
                duplicateParent:
                    val.severity === "ERROR" || val.severity === "CRITICAL"
                        ? (duplicateParents[val.severity]?.[idx] !== undefined
                            ? { severity: val.severity, index: duplicateParents[val.severity][idx] }
                            : null)
                        : null,
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
                parsed.duplicates = val.duplicates;
                parsed.index = val.index;
                parsed.duplicateParent = val.duplicateParent;
            } catch (error) {
                parsed = {
                    time: new Date(0),
                    parsed: false,
                    text: val.text,
                    error: error.message,
                    severity: val.severity,
                    similars: val.similars,
                    duplicates: val.duplicates,
                    index: val.index,
                    duplicateParent: val.duplicateParent,
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
                // Check if we have any data from the similar events service
                hasSimilarEventsData = data.response && data.response.length > 0;

                if (hasSimilarEventsData) {
                    // Create a map of event index to similars set with severity prefix
                    eventEmbeddings = data.response.reduce((acc, item) => {
                        acc[`${item.severity}_${item.event_index}`] = item.similars_set;
                        return acc;
                    }, {});

                    // Create a map of event index to duplicates list with severity prefix
                    eventDuplicates = data.response.reduce((acc, item) => {
                        acc[`${item.severity}_${item.event_index}`] = item.duplicates_list || [];
                        return acc;
                    }, {});

                    // Find duplicate pairs and mark events to hide
                    const { distinct, parentMap } = buildDistinctEvents(data.response);
                    distinctEvents = distinct;
                    duplicateParents = parentMap;
                } else {
                    duplicateParents = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };
                    distinctEvents = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };
                }
            }
        } catch (error) {
            console.error("Failed to fetch event embeddings:", error);
            sendMessage("error", "Failed to fetch event embeddings", "StructuredEvent::toggleSimilars");
            hasSimilarEventsData = false;
            duplicateParents = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };
            distinctEvents = { ERROR: {}, CRITICAL: {}, WARNING: {}, NORMAL: {}, DEBUG: {} };
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
    <div class="p-2 event-container" bind:this={eventContainer}>
        <div class="d-flex flex-wrap align-items-center gap-2 mb-2 rounded bg-light p-1 justify-content-between">
            <button
                class="btn btn-sm btn-outline-primary"
                onclick={toggleAllDuplicates}
                disabled={!hasDuplicateEvents()}
            >
                {#if allDuplicatesShown()}
                    Hide All Duplicates
                {:else}
                    Show All Duplicates
                {/if}
            </button>
            <div class="d-flex justify-content-end flex-wrap">
                {#each Object.entries(displayCategories) as [category, info]}
                    <!-- svelte-ignore a11y_label_has_associated_control -->
                    <button
                        class="ms-2 px-2 py-1 btn severity-{category.toLowerCase()}"
                        onclick={() => (info.show = !info.show)}
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
        </div>
        <div class="p-2">
            <input class="form-control" type="text" placeholder="Filter events" bind:value={filterString} />
        </div>
        {#each parsedEvents as event}
            {#if event.parsed}
                <StructuredEvent
                    bind:filterString
                    display={(displayCategories[event.severity].show ?? true) &&
                        (event.severity === "ERROR" || event.severity === "CRITICAL"
                            ? !hasSimilarEventsData ||
                              distinctEvents[event.severity].hasOwnProperty(event.index) ||
                              shownDuplicates[event.severity].has(event.index)
                            : true)}
                    {event}
                    similars={event.similars}
                    duplicates={getNumberOfDuplicates(event)}
                    duplicatesVisible={areDuplicatesVisible(event)}
                    duplicateParent={event.duplicateParent}
                    {toggleDuplicates}
                    on:issueAttach
                />
            {:else}
                <RawEvent eventText={event.text} errorMessage={event.error} />
            {/if}
        {/each}
    </div>
{:else if isLoading}
    <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center event-container">
        <span class="spinner-border me-4"></span><span class="fs-4">Loading...</span>
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
