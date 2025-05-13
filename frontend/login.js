import Login from "./Profile/Login.svelte";


const app = new Login({
    target: document.querySelector("div#loginContainer"),
    props: {
        csrfToken: CSRF_TOKEN,
        githubCid: GITHUB_CLIENT_ID,
        githubScopes: GITHUB_SCOPES,
        methods: LOGIN_METHODS,
    }
});
