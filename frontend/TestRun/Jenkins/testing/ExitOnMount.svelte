<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";

    // Stands in for a dialog step that the user completes at once.
    const dispatch = createEventDispatcher();

    onMount(() => {
        dispatch("exit", {
            newName: "cloned-test",
            target: "target-release",
            group: "target-group",
            advancedSettings: false,
            newBuildId: "fork/cloned-test",
            newTestId: "b2c3d4e5-0000-4000-8000-000000000002",
        });
    });
</script>
