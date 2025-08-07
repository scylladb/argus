<script>
    import { run } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import * as urlSlug from "url-slug";
    const dispatch = createEventDispatcher();
    let newRelease = $state({
        release_name: "",
        pretty_name: "",
        perpetual: false,
    });
    run(() => {
        newRelease.release_name = urlSlug.convert(newRelease.pretty_name);
    });

    const handleReleaseCreate = function() {
        dispatch("releaseCreate", newRelease);
    };

    const handleReleaseCreationCancel = function() {
        dispatch("releaseCreateCancel");
    };
</script>

<div class="position-fixed popup-release-creator">
    <div class="row h-100 justify-content-center align-items-center">
        <div class="col-5 rounded bg-white text-start shadow-sm p-2">
            <div class="form-group">
                <label for="" class="form-label">New Release name</label>
                <input
                    type="text"
                    class="form-control"
                    disabled
                    bind:value={newRelease.release_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Friendly name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={newRelease.pretty_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Perpetual release</label>
                <input
                    type="checkbox"
                    class="form-input-check"
                    bind:checked={newRelease.perpetual}
                />
            </div>
            <div class="mt-2 text-end">
                <button
                    class="btn btn-secondary"
                    onclick={handleReleaseCreationCancel}
                >
                    Cancel
                </button>
                <button class="btn btn-success" onclick={handleReleaseCreate}>
                    Create
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-release-creator {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }
</style>
