<script lang="ts">
    import { self } from 'svelte/legacy';

    import { createEventDispatcher, onMount } from "svelte";
    import Fa from "svelte-fa";
    import { Modal } from "bootstrap/dist/js/bootstrap.esm";
    import { faEdit, faTrash } from "@fortawesome/free-solid-svg-icons";
    let { group = $bindable(), groups } = $props();
    const dispatch = createEventDispatcher();
    let editing = $state(false);
    let editedGroup = $state(Object.assign({}, group));
    let modal = $state();
    let deleteTests = $state(true);
    let newGroupId = $state("");

    const handleGroupUpdate = function (e) {
        e.stopPropagation();
        dispatch("groupUpdate", {
            group_id: editedGroup.id,
            name: editedGroup.name,
            pretty_name: editedGroup.pretty_name,
            build_system_id: editedGroup.build_system_id,
            enabled: editedGroup.enabled,
        });
    };

    const handleGroupDelete = function (e) {
        e.stopPropagation();
        dispatch("groupDelete", {
            group_id: group.id,
            delete_tests: deleteTests,
            new_group_id: newGroupId,
        });
    };

    const handleVisibilityToggle = function(e) {
        e.stopPropagation();
        dispatch("visibilityToggleGroup", {
            groupId: group.id,
            enabled: !group.enabled,
        });
    };

    onMount(() => {
        newGroupId = groups?.[0]?.id ?? "";
    });
</script>

<div class="d-flex align-items-center w-100">
    <div>
        {group.name} {#if group.pretty_name}
            [{group.pretty_name}]
        {/if}
    </div>
    <div class="ms-auto">
        <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" role="switch" onclick={handleVisibilityToggle} bind:checked={group.enabled}>
        </div>
    </div>
    <div class="ms-2">
        <button
            class="btn btn-light"
            title="Edit"
            onclick={(e) => {
                e.stopPropagation();
                editing = true;
            }}
        >
            <Fa icon={faEdit} />
        </button>
    </div>
    <div class="ms-2">
        <button
            class="btn btn-light"
            title="Delete"
            onclick={(e) => {
                e.stopPropagation();
                Modal.getOrCreateInstance(modal).show();
            }}
        >
            <Fa icon={faTrash} />
        </button>
    </div>
</div>

<div class="position-fixed popup-group-editor" class:d-none={!editing}  onclick={(e) => e.stopPropagation()}>
    <div
        class="row justify-content-center align-items-center h-100"
        onmousedown={self(() => {
            editing = false;
        })}
    >
        <div class="col-4 mt-6 bg-white rounded shadow-sm shadow-light p-2">
            <div class="fs-6 text-muted mb-2">
                <span class="fw-bold">Argus Group Id</span>: {editedGroup.id}
            </div>
            <div class="form-group">
                <label for="" class="form-label">Group name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedGroup.name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Friendly name</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedGroup.pretty_name}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Build System Id</label>
                <input
                    type="text"
                    class="form-control"
                    bind:value={editedGroup.build_system_id}
                />
            </div>
            <div class="form-group">
                <label for="" class="form-label">Enabled</label>
                <input
                    type="checkbox"
                    class="form-check-input"
                    bind:checked={editedGroup.enabled}
                />
            </div>
            <div class="mt-2 text-end">
                <button
                    class="btn btn-secondary"
                    onclick={() => (editing = false)}
                >
                    Cancel
                </button>
                <button class="btn btn-success" onclick={handleGroupUpdate}>
                    Update
                </button>
            </div>
        </div>
    </div>
</div>

<div
    class="modal group-delete-modal position-fixed"
    tabindex="-1"
    bind:this={modal}
    id="modalGroupConfirmDelete-{editedGroup.id}"
    onclick={(e) => e.stopPropagation()}
>
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Deleting a group</h5>
                <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="modal"
                    aria-label="Close"
></button>
            </div>
            <div class="modal-body">
                <p>
                    Are you sure you want to delete group <span class="fw-bold"
                        >{editedGroup.name}</span
                    >?
                </p>
                <div class="form-group">
                    <label for="" class="form-label">Also delete associated tests</label>
                    <input
                        type="checkbox"
                        class="form-check-input"
                        bind:checked={deleteTests}
                    />
                </div>
                {#if !deleteTests}
                    <div class="form-group">
                        <label for="" class="form-label">Select new group for orphaned tests</label>
                        <select
                            class="form-select"
                            id=""
                            bind:value={newGroupId}
                        >
                            {#each groups as group (group.id)}
                                <option value={group.id}
                                    >{group.pretty_name || group.name}</option
                                >
                            {/each}
                        </select>
                    </div>
                {/if}
            </div>
            <div class="modal-footer">
                <button
                    type="button"
                    class="btn btn-secondary"
                    data-bs-dismiss="modal"
                    >No</button
                >
                <button
                    type="button"
                    class="btn btn-danger"
                    data-bs-dismiss="modal"
                    onclick={handleGroupDelete}
                >
                    Yes
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .popup-group-editor {
        background-color: rgba(0, 0, 0, 0.5);
        color: black;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 999;
    }

    .group-delete-modal {
        color: black;
    }
</style>
