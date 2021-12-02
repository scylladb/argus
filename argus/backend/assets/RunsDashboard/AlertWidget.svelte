<script>
    import { alertStore } from "./AlertStore.js";
    import { onDestroy } from "svelte";
    import AlertMessage from "./AlertMessage.svelte";
    import { v4 as uuidv4 } from 'uuid';
    export let flashes = [];

    let messages = [];
    messages = flashes.map((val) => {
        return {
            id: uuidv4(),
            type: val[0],
            message: val[1],
        };
    });

    const handleCloseEvent = function(e) {
        messages = messages.filter((value) => {
            return value.id != e.detail.id;
        });
    };

    const unsubscribe = alertStore.subscribe((value) => {
        if (value?.id) {
            messages = [...messages, value];
        };
    });

    onDestroy(unsubscribe);
</script>

<div class="position-absolute top-0 start-0">
    {#each messages as message (message.id)}
        <AlertMessage {message} on:deleteMessage={handleCloseEvent}/>
    {/each}
</div>
