<script>
    import Event from "./Event.svelte";
    export let testRun;
</script>

<div class="accordion accordion-flush" id="accordionEvents">
    {#each testRun.events as event_container}
        <div class="accordion-item">
            <h2
                class="accordion-header"
                id="accordionHeadingEvents{event_container.severity}-{testRun.id}"
            >
                <button
                    class="accordion-button collapsed"
                    type="button"
                    data-bs-toggle="collapse"
                    data-bs-target="#accordionBodyEvents{event_container.severity}-{testRun.id}"
                >
                    {event_container.severity.toUpperCase()}
                    ({event_container.event_amount})
                </button>
            </h2>
            <div
                id="accordionBodyEvents{event_container.severity}-{testRun.id}"
                class="accordion-collapse collapse"
                data-bs-parent="#accordionEvents"
            >
                <div class="accordion-body">
                    {#each event_container.last_events as event}
                        <Event eventText={event} />
                    {/each}
                </div>
            </div>
        </div>
    {:else}
        <div class="row">
            <div class="col text-center p-1 text-muted">
                No events submitted yet.
            </div>
        </div>
    {/each}
</div>
