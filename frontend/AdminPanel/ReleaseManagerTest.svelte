<script>
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faEdit,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    export let test;
    export let releaseData;
    const dispatch = createEventDispatcher();
    let editing = false;
    let editedTest = Object.assign({}, test);

    const handleTestUpdate = function () {
        dispatch("testUpdate", {
            test_id: editedTest.id,
            name: editedTest.name,
            pretty_name: editedTest.pretty_name,
            enabled: editedTest.enabled,
            build_system_id: editedTest.build_system_id,
            build_system_url: editedTest.build_system_url,
            group_id: editedTest.group_id,
        });
    };

    const handleTestDelete = function () {
        dispatch("testDelete", {
            test_id: editedTest.id
        });
    };
</script>

<li class="list-group-item d-flex align-items-center">
    <div>
        {test.name}
    </div>
    <div class="ms-auto">
        <button
            class="btn btn-light"
            title="Edit"
            on:click={() => (editing = true)}
        >
            <Fa icon={faEdit} />
        </button>
    </div>
    <div class="ms-2">
        <button
            class="btn btn-light"
            title="Delete"
            data-bs-toggle="modal"
            data-bs-target="#modalTestConfirmDelete-{editedTest.id}"
        >
            <Fa icon={faTrash} />
        </button>
    </div>
</li>

<div class="position-fixed popup-test-editor" class:d-none={!editing}>
    <div
        class="row justify-content-center align-items-center h-100"
        on:click|self={() => {
            editing = false;
        }}
    >
        <div class="col-4 mt-6 bg-white rounded shadow-sm shadow-light p-2">
            <div class="fs-6 text-muted mb-2">
                <span class="fw-bold">Argus Test Id</span>: {editedTest.id}
            </div>

            <div class="form-group">
                <label for="" class="form-label">Build System Id</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedTest.build_system_id}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Build System URL</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedTest.build_system_url}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Test name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedTest.name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Friendly name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedTest.pretty_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Group</label>
                <select
                    class="form-select"
                    id=""
                    bind:value={editedTest.group_id}
                >
                    {#each Object.values(releaseData.groups) as group (group.id)}
                        <option value={group.id}
                            >{group.pretty_name || group.name}</option
                        >
                    {/each}
                </select>
            </div>
            <div class="form-group">
                <label for="" class="form-label">Enabled</label>
                <input
                    type="checkbox"
                    class="form-check-input"
                    bind:checked={editedTest.enabled}
                />
            </div>
            <div class="mt-2 text-end">
                <button
                    class="btn btn-secondary"
                    on:click={() => (editing = false)}
                >
                    Cancel
                </button>
                <button class="btn btn-success" on:click={handleTestUpdate}>
                    Update
                </button>
            </div>
        </div>
    </div>
</div>

<div class="modal" tabindex="-1" id="modalTestConfirmDelete-{editedTest.id}">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Deleting an issue</h5>
                <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="modal"
                    aria-label="Close"
                />
            </div>
            <div class="modal-body">
                <p>
                    Are you sure you want to delete <span class="fw-bold"
                        >{editedTest.name} ({editedTest.build_system_id})</span
                    >?
                </p>
            </div>
            <div class="modal-footer">
                <button
                    type="button"
                    class="btn btn-secondary"
                    data-bs-dismiss="modal">No</button
                >
                <button
                    type="button"
                    class="btn btn-danger"
                    data-bs-dismiss="modal"
                    on:click={handleTestDelete}
                >
                    Yes
                </button>
            </div>
        </div>
    </div>
</div>


<style>
    .popup-test-editor {
        background-color: rgba(0, 0, 0, 0.5);
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }
</style>
