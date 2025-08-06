<script>
    import { createEventDispatcher } from "svelte";
    const dispatch = createEventDispatcher();
    let { tests, groups } = $props();

    let selectedGroup = $state(tests.length > 0 ? tests[0].group_id : undefined);
    let selectedTests = $state([]);

    const handleTestsMove = function () {
        dispatch("testsMove", {
            new_group_id: selectedGroup,
            tests: selectedTests,
        });
    };

    const handleCancel = function () {
        dispatch("testsMoveCancel");
    };
</script>

<div class="position-fixed popup-test-mover">
    <div class="row h-100 justify-content-center align-items-center">
        <div class="col-5 rounded bg-white shadow-sm p-2">
            <div class="form-group mb-2">
                <label for="" class="form-label">Target group</label>
                <select id="" class="form-select" bind:value={selectedGroup}>
                    {#each groups as group}
                        <option value={group.id}
                            >{group.pretty_name || group.name}</option
                        >
                    {/each}
                </select>
            </div>
            <div class="form-group mb-2">
                <label for="" class="form-label">Tests</label>
                <select
                    name=""
                    multiple
                    class="form-select"
                    size=16
                    bind:value={selectedTests}
                >
                    {#each tests.sort((a, b) => a.name > b.name ? 1 : -1) as test (test.id)}
                        <option value={test.id}
                            >{test.name ?? test.pretty_name}</option
                        >
                    {/each}
                </select>
            </div>
            <div class="form-group text-end">
                <button class="btn btn-secondary" onclick={handleCancel}>
                    Cancel
                </button>
                <button class="btn btn-success" onclick={handleTestsMove}>
                    Move
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-test-mover {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }
</style>
