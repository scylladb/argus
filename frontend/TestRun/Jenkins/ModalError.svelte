<script>

    /**
     * @typedef {Object} Props
     * @property {any} args
     */

    /** @type {Props} */
    let { args } = $props();
</script>

<div class="alert alert-danger">
    <pre style="white-space: pre-wrap;">{args.message}</pre>
</div>
