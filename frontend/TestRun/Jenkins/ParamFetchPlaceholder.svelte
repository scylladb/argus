<script>

    /**
     * @typedef {Object} Props
     * @property {{buildId: string, buildNumber: string}} args
     */

    /** @type {Props} */
    let { args } = $props();
</script>

<div>
    <span class="spinner-border spinner-border-sm"></span> Fetching parameters from {args.buildId}#{args.buildNumber}...
</div>
