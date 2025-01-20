<script>
    import { faCopy, faDotCircle } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";


    export let event;
    export let display = true;
    export let filterString = "";

    let displayShortPeriodBlock = true;

    const shouldFilter = function (filterString) {
        if (!filterString) return;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((event.eventText.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

</script>


<div
    class:d-none={!display || shouldFilter(filterString)}
    class="mb-2 p-2 shadow rounded bg-white font-monospace"
>
    <div class="event-header d-flex align-items-start flex-wrap">
        <div class="ms-2 mb-2 bg-dark text-light rounded px-2">{event.eventType}</div>
        <div class="ms-2 mb-2 rounded px-2 severity-{event.severity.toLowerCase()}">{event.severity}</div>
        {#each event.nemesis ?? [] as nemesis}
            <div class="ms-2 mb-2 rounded px-2 status-{nemesis.status.toLowerCase()}">{nemesis.name}</div>
        {/each}
        <div class="ms-auto mb-2 rounded px-2">
            <button
                class="btn btn-light"
                on:click={() => {
                    navigator.clipboard.writeText(event.eventText);
                    sendMessage("success", "Event text has been copied to your clipboard");
                }}
            >
                <Fa icon={faCopy} />
            </button>
        </div>
        <div class="w-100"></div>
        <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">{event.eventTimestamp}</div>
        {#if event.receiveTimestamp}
            <div class="ms-2 mb-2 rounded px-2 bg-warning" title="Timestamp">Received: {event.receiveTimestamp}</div>
        {/if}
        {#if !displayShortPeriodBlock}
            <div
                role="button"
                class="ms-auto mb-2 rounded px-2 bg-light-two"
                title="Period type"
                on:click={() => (displayShortPeriodBlock = !displayShortPeriodBlock)}
            >
                <div>Event period type: {event.fields.period_type}</div>
                {#if event.fields.start}
                    <div>Start: {event.fields.start}</div>
                {/if}
                {#if event.fields.end}
                    <div>End: {event.fields.end}</div>
                    <div>Duration: {event.fields.duration}</div>
                {/if}
            </div>
        {:else}
            <div
                role="button"
                class="ms-auto mb-2 rounded px-2 bg-light-two d-flex align-items-center"
                title="Period type"
                on:click={() => (displayShortPeriodBlock = !displayShortPeriodBlock)}
            >
                <Fa icon={faDotCircle}/> <span class="ms-2">{event.fields.period_type}</span>
            </div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.node}
            <div class="ms-2 mb-2 rounded px-2 bg-info fs-6 justify-self-start">{event.fields.node}</div>
        {/if}
        {#if event.fields.target_node}
            <div class="ms-2 mb-2 rounded px-2 bg-info fs-6 justify-self-start">{event.fields.target_node}</div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.known_issue}
            <div class="ms-2 mb-2 rounded px-2 bg-info fs-6 justify-self-start">Known issue: <a href="{event.fields.known_issue}" class="link-dark">{event.fields.known_issue}</a></div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.nemesis_name}
            <div class="ms-2 mb-2 rounded px-2 bg-dark text-light fs-6 justify-self-start">Nemesis: {event.fields.nemesis_name}</div>
        {/if}
    </div>
    <pre class="bg-light-one rounded m-2 p-2 log-line">{event.eventText}</pre>
</div>

<style>
    .log-line {
        white-space: pre-wrap
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
    .status-succeeded {
        background-color: #198754;
        color: white;
    }
    .status-failed {
        background-color: #dc3545;
        color: white;
    }
    .status-skipped {
        background-color: #1c1f23;
        color: white;
    }
</style>
