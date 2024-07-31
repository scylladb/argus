<script>
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import Fa from "svelte-fa";

    export let csrfToken;
    export let githubCid;
    export let githubScopes;
    export let methods = [];

    /**
     * @type {boolean}
     */
    let disableRepoAccess = JSON.parse(localStorage.getItem("loginPageDisableFullRepoAccess")) ?? false;

    /**
     * @param {string} rawScopes
     * @param {boolean} fullAccess
     * @returns {string}
     */
    const parseScopes = function(rawScopes, fullAccess) {
        /**
         * @type {{ string: boolean }} Scopes
         */
        let scopes = rawScopes
            .split(/\s/)
            .reduce((acc, scope) => {
                acc[scope] = scope == "repo" ? !fullAccess : true;
                return acc;
            }, {});

        return Object
            .entries(scopes)
            .filter(([_, enabled]) => enabled)
            .map(([scope, _]) => scope)
            .join(" ");
    };

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
                    <input type="hidden" name="scope" value={parseScopes(githubScopes, disableRepoAccess)} />
                    <input type="hidden" name="client_id" value={githubCid} />
                    <input type="hidden" name="state" value={csrfToken} />
                    <button class="btn btn-dark" type="submit"><Fa icon={faGithub}/> Sign In with GitHub</button>
                </form>
                <div class="mb-3">
                    <label for="disableRepoAccess" class="form-check-label">Disable full repo access</label>
                    <input
                        id="disableRepoAccess"
                        type="checkbox"
                        class="form-check-input"
                        bind:checked={disableRepoAccess}
                        on:change={() => {
                            localStorage.setItem("loginPageDisableFullRepoAccess", `${disableRepoAccess}`);
                        }}
                    >
                </div>
            </div>
        {/if}
        {#if methods.length == 0}
            <div class="alert alert-danger my-2">
                No login methods available. Change LOGIN_METHODS config variable.
            </div>
        {/if}
    </div>
</div>
