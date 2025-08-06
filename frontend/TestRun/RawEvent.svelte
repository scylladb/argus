<script lang="ts">

    let { eventText, errorMessage } = $props();

</script>

<div class="mb-1 p-1 shadow rounded bg-white font-monospace">
    {#if errorMessage}
        <div>{errorMessage}</div>
    {/if}
    <pre>{eventText.trim()}</pre>
</div>
