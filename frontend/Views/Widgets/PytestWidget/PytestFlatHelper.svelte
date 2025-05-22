<script>
    import { createEventDispatcher, onMount } from "svelte";

    const dispatch = createEventDispatcher();

    onMount(() => {
        dispatch("open");
    });
</script>
<slot>

</slot>
