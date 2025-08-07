<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import ReleaseDeletionConfirmationPopup from "./ReleaseDeletionConfirmationPopup.svelte";
    const dispatch = createEventDispatcher();
    let { releaseData = $bindable() } = $props();

    let awaitingConfirmation = $state(false);

    const handleReleaseEdit = function() {
        dispatch("releaseEdit", releaseData);
    };

    const handleReleaseEditCancel = function() {
        dispatch("releaseEditCancel");
    };

    const handleReleaseDelete = function() {
        awaitingConfirmation = false;
        dispatch("releaseDelete", {
            releaseId: releaseData.id
        });
    };
</script>

<div class="position-fixed popup-release-editor">
    <div class="row h-100 justify-content-center align-items-center">
        <div class="col-5 rounded bg-white text-start shadow-sm p-2">
            <h6 class="text-secondary"><span class="fw-bold">Release name:</span> {releaseData.name}</h6>
            <div class="form-group">
                <label for="" class="form-label">Friendly name</label>
                <input
                    type="text"
                    class="form-control"
                    placeholder="Example: ScyllaDB Enterprise 2024.1"
                    bind:value={releaseData.pretty_name}
                />
                <label for="" class="form-label">Version Regex</label>
                <input
                    type="text"
                    class="form-control"
                    placeholder="Example: 2024.1(.*)"
                    bind:value={releaseData.valid_version_regex}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label mb-0">Weekly schedules</label>
                <input
                    type="checkbox"
                    class="form-input-check"
                    bind:checked={releaseData.perpetual}
                />
            </div>

            <div class="form-group">
                <label for="" class="form-label mb-0">Disable stats fetching</label>
                <input
                    type="checkbox"
                    class="form-input-check"
                    bind:checked={releaseData.dormant}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label mb-0">Show release</label>
                <input
                    type="checkbox"
                    class="form-input-check"
                    bind:checked={releaseData.enabled}
                />
            </div>
            <div class="mt-2 text-end">
                <button
                    class="btn btn-danger"
                    onclick={() => (awaitingConfirmation = true)}
                >
                    Delete Release
                </button>
                {#if awaitingConfirmation}
                    <ReleaseDeletionConfirmationPopup {releaseData} on:deletionConfirmed={handleReleaseDelete} on:deletionCanceled={() => (awaitingConfirmation = false)}/>
                {/if}
                <button
                    class="btn btn-secondary"
                    onclick={handleReleaseEditCancel}
                >
                    Cancel
                </button>
                <button class="btn btn-success" onclick={handleReleaseEdit}>
                    Update
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-release-editor {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }
</style>
