<script>
    export let state;
</script>

<div class="bg-white m-2">
    <div class="{state.classes.join(" ")} rounded text-center p-2"
    >{#if state?.inProgress}
        <span class="spinner-border spinner-border-sm"></span>
    {/if} {state.message} <slot></slot></div>
</div>
