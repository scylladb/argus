<script lang="ts">
    import { PytestResult } from "./ViewPytestOverview.svelte";

    export let test: PytestResult;
</script>

<div class="mb-2">
    <div class="d-flex">
        <div>
            {test.name}
        </div>
        <div class="ms-2 rounded bg-dark text-light px-2">
            {test.status}
        </div>
    </div>
</div>
