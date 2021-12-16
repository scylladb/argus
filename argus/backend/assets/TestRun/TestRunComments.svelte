<script>
    import { onMount } from "svelte";
    import { parse } from "marked";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";

    export let id;
    let comments = [];
    let user_info = {};
    let new_comment = "";
    let fetching = false;

    userList.subscribe((val) => {
        user_info = val;
    });

    const getPictureForId = function (id) {
        let picture_id = user_info[id]?.picture_id;
        return picture_id
            ? `/storage/picture/${picture_id}`
            : "/static/no-user-picture.png";
    };

    const fetchComments = async function () {
        fetching = true;
        comments = {};
        try {
            let apiResponse = await fetch("/api/v1/test_run/comments", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    test_id: id,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                comments = apiJson.response;
                fetching = false;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch comments.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during comments fetch"
                );
            }
        }
    };

    const handleCommentSubmit = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch("/api/v1/test_run/comments/submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    test_id: id,
                    message: new_comment,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                comments = apiJson.response;
                sendMessage("success", "Successfully posted a comment!")
                fetching = false;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching releases.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release fetch"
                );
            }
        }
        new_comment = "";
    };
    onMount(() => {
        fetchComments();
    });
</script>

<div class="container-fluid py-1 m-0">
    {#if Object.keys(user_info).length > 0}
        {#each comments as comment (comment.id)}
            <div class="row p-0 m-0">
                <div class="col-1 p-1 mb-1 text-center">
                    <img
                        class="img-profile"
                        src={getPictureForId(comment.user_id)}
                        alt=""
                    />
                </div>
                <div class="col-11 p-0 mb-1">
                    <div class="card-body border-bottom">
                        <h5
                            class="card-title"
                            title={user_info[comment.user_id]?.username ??
                                "ghost"}
                        >
                            {user_info[comment.user_id]?.full_name ?? "Ghost"}
                        </h5>
                        <p class="card-text">{@html parse(comment.message)}</p>
                        <p class="card-text">
                            <small class="text-muted"
                                >{new Date(
                                    comment.posted_at * 1000
                                ).toLocaleString()}</small
                            >
                        </p>
                    </div>
                </div>
            </div>
        {:else}
            <div class="row">
                <div class="col text-center p-1 text-muted">
                    No comments yet.
                </div>
            </div>
        {/each}
    {:else}
        loading...
    {/if}
    <div class="row">
        <div class="col mb-3">
            <div class="mb-3">
                <label for="add-comment-{id}" class="form-label"
                    >Add a comment</label
                >
                <textarea
                    class="form-control"
                    id="add-comment-{id}"
                    rows="4"
                    bind:value={new_comment}
                />
            </div>
            <button
                type="button"
                class="btn btn-success"
                on:click={handleCommentSubmit}
                placeholder="Type a comment."
                disabled={fetching}>Post</button
            >
        </div>
    </div>
</div>

<style>
    .img-profile {
        height: 72px;
        border-radius: 50%;
        object-fit: cover;
    }
</style>
