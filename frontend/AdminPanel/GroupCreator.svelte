<script>
    import { run } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import * as urlSlug from "url-slug";
    const dispatch = createEventDispatcher();
    /**
     * @typedef {Object} Props
     * @property {string} [releaseId]
     */

    /** @type {Props} */
    let { releaseId = "" } = $props();
    let newGroup = $state({
        group_name: "",
        pretty_name: "",
        build_system_id: "",
    });

    run(() => {
        newGroup.group_name = urlSlug.convert(newGroup.pretty_name);
    });

    const handleGroupCreate = function() {
        dispatch("groupCreate", Object.assign({
            release_id: releaseId,
        }, newGroup));
    };

    const handleGroupCreationCancel = function() {
        dispatch("groupCreateCancel");
    };
</script>

<div class="position-fixed popup-group-creator">
    <div class="row h-100 justify-content-center align-items-center">
        <div class="col-5 rounded bg-white shadow-sm p-2">
            <div class="form-group">
                <label for="" class="form-label">New group name</label>
                <input
                    type="text"
                    class="form-control"
                    disabled
                    bind:value={newGroup.group_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Friendly name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={newGroup.pretty_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Build System Id</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={newGroup.build_system_id}
                />
            </div>
            <div class="mt-2 text-end">
                <button
                    class="btn btn-secondary"
                    onclick={handleGroupCreationCancel}
                >
                    Cancel
                </button>
                <button class="btn btn-success" onclick={handleGroupCreate}>
                    Create
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-group-creator {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }
</style>
