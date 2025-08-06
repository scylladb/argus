<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    const dispatch = createEventDispatcher();
    let { releaseData } = $props();
    let releaseNameForConfirmation = $state("");

    const confirm = function() {
        if (releaseNameForConfirmation != releaseData.name) {
            sendMessage("error", "Release name doesn't match.", "ReleaseDelete::confirm");
            return;
        }
        dispatch("deletionConfirmed");
    };

    const cancel = function() {
        dispatch("deletionCanceled");
    };

</script>

<div class="position-fixed popup-release-deletion">
    <div class="row h-100 justify-content-center align-items-center">
        <div class="col-5 rounded bg-white text-start shadow-sm p-2">
            <h5 class="fw-bold">Deleting release: {releaseData.name} {releaseData.pretty_name ? `(${releaseData.pretty_name})` : ""}</h5>
            <div>
                This will delete the release and all its associated groups and tests. This operation is irreversible. Are you sure?

                <p class="text-secondary">Note: Runs submitted for this release will be preserved, but will require manual intervention to work with again.</p>
            </div>
            <div>
                <div class="form-group">
                    <label for="" class="form-label">Type the release name to confirm:</label>
                    <input
                        type="text"
                        class="form-control"
                        bind:value={releaseNameForConfirmation}
                    />
                </div>
            </div>
            <div class="mt-2 mb-1">
                <button class="btn btn-danger w-100" onclick={() => confirm()}>
                    I understand. Delete the release.
                </button>
            </div>
            <div>
                <button class="btn btn-secondary w-100" onclick={() => cancel()}>
                    Cancel
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-release-deletion {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 1001;
    }
</style>
