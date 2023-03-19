<script>
    export let event;
    export let display = true;
    export let filterString = "";

    let displayShortPeriodBlock = true;

    const shouldFilter = function (filterString) {
        if (!filterString) return;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((event.logLine.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

</script>


<div
    class:d-none={!display || shouldFilter(filterString)}
    class="mb-2 p-2 shadow rounded bg-white font-monospace"
>
    <div class="event-header d-flex justify-content-end flex-wrap">
        <div class="ms-2 mb-2 bg-dark text-light rounded px-2">{event.eventType}</div>
        <div class="ms-2 mb-2 me-auto rounded px-2 severity-{event.severity.toLowerCase()}">{event.severity}</div>
        <div class="w-100"></div>
        {#if !["one-time", "not-set"].includes(event.fields.period_type)}
            {#if !displayShortPeriodBlock}
                <div
                    role="button"
                    class="ms-2 mb-2 rounded px-2 bg-light-two"
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
                    class="ms-2 mb-2 rounded px-2 bg-light-two"
                    title="Period type"
                    on:click={() => (displayShortPeriodBlock = !displayShortPeriodBlock)}
                >
                    <div>{event.fields.period_type}</div>
                </div>
            {/if}
        {/if}
        <div class="w-100"></div>
        <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">{event.eventTimestamp}</div>
        {#if event.receiveTimestamp}
            <div class="ms-2 mb-2 rounded px-2 bg-warning" title="Timestamp">Received: {event.receiveTimestamp}</div>
        {/if}

        {#if event.fields.node}
            <div class="w-100"></div>
            <div class="ms-2 rounded px-2 bg-info fs-6 justify-self-start">{event.fields.node}</div>
        {/if}
    </div>
    <pre class="bg-light-one rounded m-2 p-2 log-line">{event?.message ?? ""}{event.logLine}</pre>
</div>

<style>
    .log-line {
        white-space: pre-wrap
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
