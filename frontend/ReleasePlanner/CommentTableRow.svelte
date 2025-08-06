<script lang="ts">
    import Fa from "svelte-fa";
    import { faEdit, faSave } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    interface Props {
        release?: string;
        group?: string;
        test?: string;
        commentText?: string;
        autocompleteList?: any;
    }

    let {
        release = "",
        group = "",
        test = "",
        commentText = $bindable(""),
        autocompleteList = []
    }: Props = $props();
    let editing = $state(false);
    let updating = $state(false);

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
                onclick={() => { updateScheduleComment(); }}
            >
                <Fa icon={faSave} />
            </button>
        {:else if updating}
            <!-- Nothing -->
        {:else}
            <button
                class="btn btn-dark btn-sm"
                onclick={() => { editing = true; }}
            >
                <Fa icon={faEdit} />
            </button>
        {/if}
    </div>
</div>

<style>

</style>
