<script lang="ts">
    import { faEdit, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";

    let { view } = $props();
    let deleting = $state(false);
    const dispatch = createEventDispatcher();

    const resolveViewForUpdating = async function () {
        try {
            const response = await fetch(`/api/v1/views/${view.id}/resolve`);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            console.log(json.response);

            dispatch("viewUpdateRequested", json.response);
        } catch (error) {
            console.log(error);
        }
    };
</script>

<div class="d-flex align-items-center rounded bg-white p-2 border shadow-sm mb-2">
    <div>
        <div class="fw-bold">{view.display_name || view.name}</div>
        <div>Contains {view.tests.length} tests.</div>
        <div class="text-muted">
            {view.description || "No description provided."}
        </div>
    </div>
    <div class="ms-auto"><button class="btn btn-primary" onclick={resolveViewForUpdating}><Fa icon={faEdit}/></button></div>
    <div class="ms-2"><button class="btn btn-danger" onclick={() => (deleting = true)}><Fa icon={faTrash}/></button></div>
</div>

{#if deleting}
    <div class="delete-view-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 h-50">
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Deleting <span class="fw-bold">{view.display_name || view.name}</span></h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            onclick={() => {
                                deleting = false;
                            }}
                        ></button>
                    </div>
                </div>
                <div>
                    <div>Are you sure you want to delete this view?</div>
                    <div class="d-flex justify-content-end">
                        <div><button class="btn btn-danger" onclick={() => dispatch("delete", view.id)}>Confirm</button></div>
                        <div class="ms-1"><button class="btn btn-secondary" onclick={() => (deleting = false)}>Cancel</button></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
{/if}


<style>
    .h-50 {
        width: 50%;
    }
    .delete-view-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }
</style>
