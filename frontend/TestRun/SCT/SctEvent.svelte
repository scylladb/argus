<script lang="ts">
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../../Common/DateUtils";
    import type { EventSeverityFilter, Options, SCTEvent } from "./SctEvents.svelte";
    import Fa from "svelte-fa";
    import { faClipboard, faClock, faCopy, faPlus, faServer, faSpider, faTable } from "@fortawesome/free-solid-svg-icons";
    import SctSimilarEvents from "./SctSimilarEvents.svelte";
    import { sendMessage } from "../../Stores/AlertStore";
    import { onMount } from "svelte";
    import type { GithubSubtype, JiraSubtype } from "../../Github/Issues.svelte";
    import type { SCTTestRun } from "../TestRun.svelte";
    import ModalWindow from "../../Common/ModalWindow.svelte";
    import { JiraIssueColorMap, JiraIssueIcon } from "../../Jira/JiraIssue.svelte";
    import { GithubIssueColorMap, GithubIssueIcon } from "../../Github/GithubIssue.svelte";
    import Color from "color";

    interface Props {
        event: SCTEvent,
        run: SCTTestRun,
        filterState: EventSeverityFilter,
        options: Options,
        issueAttach: (url: string) => void;
        filterString: string,
    }
    let { event, run, filterState, options, issueAttach, filterString = $bindable()}: Props = $props();
    const MESSAGE_CUTOFF = 600;
    const SHORT_MESSAGE_LEN = 500;
    let issues: (GithubSubtype | JiraSubtype)[] = $state([]);
    let showingIssueTable = $state(false);
    let showingIssueAddWindow = $state(false);
    let newIssueUrl = $state("");
    let submitting = $state(false);

    const sliceMessage = function (message: string): string {
        return fullMessage && message.length <= MESSAGE_CUTOFF ? message : message.slice(0, SHORT_MESSAGE_LEN);
    }

    const submitIssueForEvent = async function () {
        try {
            submitting = true;
            const res = await fetch(
                `/api/v1/test/${run.test_id}/run/${run.id}/issues/event/${event.event_id}/submit`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        "issue_url": newIssueUrl,
                    })
                }
            );
            const json = await res.json();
            if (json.status !== "ok") {
                throw json;
            }
            await fetchIssueForEvent();
            showingIssueAddWindow = false;
        } catch(e: any) {
            console.trace();
            console.log(e);
            sendMessage("error", "Error submitting an issue for an event!", "SctEvent::submitIssueForEvent");
        } finally {
            newIssueUrl = "";
            submitting = false;
        }
    }

    const fetchIssueForEvent = async function() {
        try {
            const res = await fetch(`/api/v1/issues/get?filterKey=event_id&id=${event.event_id}`);
            const json = await res.json();
            if (json.status !== "ok") {
                throw json;
            }
            issues = json.response;
        } catch(e: any) {
            console.trace();
            console.log(e);
            sendMessage("error", "Error getting issues for an event!", "SctEvent::fetchIssueForEvent");
        }
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
        if (!match) return null;
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

    onMount(async () => {
        await fetchIssueForEvent();
    })
</script>

{#if showingIssueTable}
    <ModalWindow on:modalClose={() => (showingIssueTable = false)}>
        {#snippet title()}
            <div>
                Issues for event <span class="fw-bold">{event.event_id}</span>
            </div>
            {/snippet}
        {#snippet body()}
            <div>
                <table class="table table-responsive table-striped table-bordered">
                    <thead>
                        <tr>
                            <th>State</th>
                            <th>Title</th>
                            <th>Labels</th>
                            <th>Added on</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each issues as issue}
                            {#if issue.subtype == "github"}
                                {@const i = issue as GithubSubtype}
                                <tr>
                                    <td>
                                        <div class="mb-1 py-1 shadow-sm rounded-pill d-inline-flex {GithubIssueColorMap[i.state]}">
                                            <div class="ms-2 me-1"><Fa icon={GithubIssueIcon[i.state]} /></div>
                                            <div class="me-2">{issue.state}</div>
                                        </div>
                                    </td>
                                    <td>
                                        <a class="link-dark" href={i.url}>{i.title}</a>
                                        <div class="text-muted">
                                            {i.owner}/{i.repo}#{i.number}
                                        </div>
                                    </td>
                                    <td>
                                        {#each i.labels as label}
                                            <div class="mb-1 text-center rounded-pill border px-1" style="color: {Color(`#${label.color}`).isDark() ? 'white' : 'black'}; background-color: #{label.color};">
                                                {label.name}
                                            </div>
                                        {/each}
                                    </td>
                                    <td>{timestampToISODate(i.added_on)}</td>
                                </tr>
                            {:else if issue.subtype == "jira"}
                                {@const i = issue as JiraSubtype}
                                <tr>
                                    <td>
                                        <div class="mb-1 py-1 shadow-sm rounded-pill d-inline-flex {JiraIssueColorMap[i.state] || JiraIssueColorMap["new"]}">
                                            <div class="ms-2 me-1"><Fa icon={JiraIssueIcon[i.state] || JiraIssueIcon["new"]} /></div>
                                            <div class="me-2">{issue.state}</div>
                                        </div>
                                    </td>
                                    <td>
                                        <a class="link-dark" href={i.permalink}>{i.summary}</a>
                                        <div class="text-muted">
                                            {i.key}
                                        </div>
                                    </td>
                                    <td>
                                        {#each i.labels as label}
                                            <div class="mb-1 text-center rounded-pill border px-1" style="color: {Color(`#${label.color}`).isDark() ? 'white' : 'black'}; background-color: #{label.color};">
                                                {label.name}
                                            </div>
                                        {/each}
                                    </td>
                                    <td>{timestampToISODate(i.added_on)}</td>
                                </tr>
                            {:else}
                                <tr>
                                    <td>{issue.state}</td>
                                    <td>{issue.id}</td>
                                    <td>{issue.labels.join("\n")}</td>
                                    <td>{timestampToISODate(issue.added_on)}</td>
                                </tr>
                            {/if}
                        {/each}
                    </tbody>
                </table>
            </div>
        {/snippet}
    </ModalWindow>
{/if}

{#if showingIssueAddWindow}
    <ModalWindow widthClass="w-50" on:modalClose={() => (showingIssueAddWindow = false)}>
        {#snippet title()}
            <div>
                Adding issue for event <span class="fw-bold">{event.event_id}</span>
            </div>
            {/snippet}
        {#snippet body()}
            <div>
                <div class="w-100 mb-2">
                    <input class="w-100 form-control" type="text" bind:value={newIssueUrl} placeholder="Issue URL (Github or Jira)">
                </div>
                <div class="mb-2">
                    Add an issue to this event. The issue will also show up in Issues tab of this run.
                </div>
                <div class="text-end">
                    <div class="btn-group">
                        <button class="btn btn-success" disabled={submitting} onclick={submitIssueForEvent}>{#if submitting}<span class="spinner-border spinner-border-sm"></span>{/if} Submit</button>
                        <button class="btn btn-secondary" disabled={submitting} onclick={() => showingIssueAddWindow = false}>Cancel</button>
                    </div>
                </div>
            </div>
        {/snippet}
    </ModalWindow>
{/if}


{#if !shouldFilter(filterString)}
    <div class="ms-3 rounded overflow-hidden shadow-sm severity-border-{event.severity.toLowerCase()}">
        <div class="border-bottom bg-titlebar text-light p-1">
            <div class="d-flex mb-1">
                <div class="rounded bg-dark p-1">{event.event_type}</div>
                <div class="ms-2 p-1 bg-light text-dark rounded">{parsedMessage ? parsedMessage.fields["period_type"] : ""}</div>
                <div class="ms-auto"></div>
                <div class="ms-2 btn-group">
                    {#if issues.length > 0}
                        <button class="btn btn-sm btn-primary" onclick={() => showingIssueTable = true}><Fa icon={faTable}/> View {issues.length} Issue{issues.length > 1 ? "s" : ""}</button>
                    {/if}
                    <button class="btn btn-sm btn-success" onclick={() => showingIssueAddWindow = true}><Fa icon={faPlus}/> {#if issues.length == 0}<span>New Issue</span>{/if}</button>
                </div>
                {#if event.duration}
                    <div class="ms-1 p-1 rounded bg-dark text-light">{humanizeDuration(event.duration * 1000, { round: true, largest: 2})}</div>
                {/if}
                <div class="ms-2 p-1 bg-light text-dark rounded">{timestampToISODate(event.ts, true)}</div>
                <button class="ms-2 btn btn-sm btn-success" onclick={() => navigator.clipboard.writeText(event.message)}><Fa icon={faCopy}/></button>
                <SctSimilarEvents {event} runId={event.run_id} issueAttach={issueAttach}/>
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
