<script lang="ts">
    let { state, children } = $props();
</script>

<div class="bg-white m-2">
    <div class="{state.classes.join(" ")} rounded text-center p-2"
    >{#if state?.inProgress}
        <span class="spinner-border spinner-border-sm"></span>
    {/if} {state.message} {@render children?.()}</div>
</div>
