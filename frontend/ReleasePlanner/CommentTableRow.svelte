<script>
    import Fa from "svelte-fa";
    import { faEdit, faSave } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    export let release = "";
    export let group = "";
    export let test = "";
    export let commentText = "";
    export let autocompleteList = [];
    let editing = false;
    let updating = false;

    const updateScheduleComment = async function() {
        editing = false;
        updating = true;
        try {
            let apiResponse = await fetch("/api/v1/release/schedules/comment/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    releaseId: release,
                    groupId: group,
                    testId: test,
                    newComment: commentText,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                commentText = apiJson.response.newComment;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to update schedule comment.\nAPI Response: ${error.response.arguments[0]}`,
                    "CommentTableRow::update"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule comment update",
                    "CommentTableRow::update"
                );
                console.log("Error: ", error);
            }
        }
        updating = false;
    };

</script>

<div class="d-flex">
    <div class="me-2  w-100">
        {#if editing}
            <div>
                <input class="form-control" type="text" bind:value={commentText} list="comment-autocomplete">
            </div>
            <datalist id="comment-autocomplete">
                {#each autocompleteList as val}
                    <option value="{val}"></option>
                {/each}
            </datalist>
        {:else if updating}
            <div>
                <span class="spinner-border spinner-border-sm"></span> Saving...
            </div>
        {:else}
            <div>
                {commentText || ""}
            </div>
        {/if}
    </div>
    <div class="ms-auto">
        {#if editing}
            <button
                class="btn btn-success btn-sm"
                on:click={() => { updateScheduleComment(); }}
            >
                <Fa icon={faSave} />
            </button>
        {:else if updating}
            <!-- Nothing -->
        {:else}
            <button
                class="btn btn-dark btn-sm"
                on:click={() => { editing = true; }}
            >
                <Fa icon={faEdit} />
            </button>
        {/if}
    </div>
</div>

<style>

</style>
