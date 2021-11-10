<script>
    import { onMount } from "svelte";
    import { parse } from "marked";

    export let id;
    let comments = {};
    let user_info = {};
    let new_comment = "";
    let fetching = false;

    const fetchUserInfo = function () {
        fetch("/api/v1/users", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({}),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error fetching users");
                    console.log(res);
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    user_info = res.response;
                    console.log(user_info);
                } else {
                    console.log("Something went wrong...");
                    console.log(res);
                }
            });
    };
    const fetchComments = function () {
        fetching = true;
        comments = {};
        fetch("/api/v1/test_run/comments", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                test_id: id,
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error fetching test run comments");
                    console.log(res);
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    fetching = false;
                    comments = res.response;
                    console.log(comments);
                } else {
                    console.log("Something went wrong...");
                    console.log(res);
                }
            });
    };

    const handleCommentSubmit = function () {
        fetch("/api/v1/test_run/comments/submit", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                test_id: id,
                message: new_comment
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error fetching test run comments");
                    console.log(res);
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    comments = res.response;
                    console.log(comments);
                } else {
                    console.log("Something went wrong...");
                    console.log(res);
                }
            });
        new_comment = "";
    };
    onMount(() => {
        fetchComments();
        fetchUserInfo();
    });
</script>

<div class="container-fluid py-1 m-0">
    {#each comments?.comments ?? [] as comment}
        <div class="row p-0 m-0">
            <div class="col-12 p-0 mb-1">
                <div class="card-body border-bottom">
                    <h5 class="card-title">{user_info[comment.user_id]?.username ?? "Ghost"}</h5>
                    <p class="card-text">{@html parse(comment.message)}</p>
                    <p class="card-text"><small class="text-muted">{new Date(comment.timestamp * 1000).toLocaleString()}</small></p>
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
    <div class="row">
        <div class="col mb-3">
            <div class="mb-3">
                <label for="add-comment-{id}" class="form-label">Add a comment</label>
                <textarea class="form-control" id="add-comment-{id}" rows="4" bind:value={new_comment}></textarea>
            </div>
            <button type="button" class="btn btn-success" on:click={handleCommentSubmit} placeholder="Type a comment." disabled={fetching}>Post</button>
        </div>
    </div>
</div>
