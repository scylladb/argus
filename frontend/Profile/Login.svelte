<script>
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import { faBook } from "@fortawesome/free-solid-svg-icons";
    import { onMount } from "svelte";
    import Fa from "svelte-fa";

    let {
        manualLogout,
        csrfToken,
        githubCid,
        githubScopes,
        methods = []
    } = $props();

    let oktaBtn = $state(null);
    let oktaText = $state("Sign in with Okta");
    onMount(() => {
        if (oktaBtn && !manualLogout) {
            oktaText = "Automatic Login with Okta starting...";
            oktaBtn.click();
        }
    })
</script>

<div class="row justify-content-center">
    <div class="col-4 text-end">
        {#if methods.includes("password")}
            <form method="post">
                <div class="mb-3">
                    <label class="form-label" for="username">Username</label>
                    <input class="form-control" name="username" id="username" required />
                </div>
                <div class="mb-3">
                    <label class="form-label" for="password">Password</label>
                    <input class="form-control" type="password" name="password" id="password" required />
                </div>
                <div class="mb-3">
                    <input class="btn btn-primary" type="submit" value="Log In" />
                </div>
            </form>
        {/if}
        {#if methods.includes("gh")}
            <div class:text-center={!methods.includes("password")} class="my-2" >
                <form action="https://github.com/login/oauth/authorize" method="get">
                    <input type="hidden" name="scope" value={githubScopes} />
                    <input type="hidden" name="client_id" value={githubCid} />
                    <input type="hidden" name="state" value={csrfToken} />
                    <button class="btn btn-dark" type="submit"><Fa icon={faGithub}/> Sign In with GitHub</button>
                </form>
            </div>
        {/if}
        {#if methods.includes("cf")}
            <div class:text-center={!methods.includes("password")} class="my-2" >
                <form action="/auth/login/cf" method="post">
                    <button class="btn btn-primary" type="submit" bind:this={oktaBtn}><Fa icon={faBook}/> {oktaText}</button>
                </form>
            </div>
        {/if}
        {#if methods.length == 0}
            <div class="alert alert-danger my-2">
                No login methods available. Change LOGIN_METHODS config variable.
            </div>
        {/if}
    </div>
</div>
