<script lang="ts">
    import queryString from "query-string";
    import ReleaseStats from "./ReleaseStats.svelte";
    let { releaseName, productVersion } = $props();

    const fetchStats = async function (force = false) {
        if (!document.hasFocus()) return Promise.reject(new Error("#noFocus"));
        let params = queryString.stringify({
            release: releaseName,
            limited: new Number(false),
            force: new Number(true),
            productVersion: productVersion ?? "",
        });
        let opts = force ? {cache: "reload"} : {};
        let response = await fetch("/api/v1/release/stats/v2?" + params, opts);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        return json.response;
    };
</script>

{#await fetchStats()}
    <span class="spinner-border spinner-border-sm"></span> Loading statistics...
{:then releaseStats}
    <ReleaseStats {releaseStats}/>
{:catch err}
    {#if err.message == "#noFocus"}
        <!-- blank -->
    {:else}
        {err.message}
    {/if}
{/await}
