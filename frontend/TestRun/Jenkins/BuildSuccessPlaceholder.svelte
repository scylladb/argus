<script>
    import queryString from "query-string";
    import { sendMessage } from "../../Stores/AlertStore";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { timestampToISODate } from "../../Common/DateUtils";
    import Fa from "svelte-fa";
    import { faArrowCircleRight } from "@fortawesome/free-solid-svg-icons";


    /**
     * @typedef {Object} Props
     * @property {any} args
     */

    /** @type {Props} */
    let { args } = $props();
    const dispatch = createEventDispatcher();

    let fetching = $state(true);
    let retrySeconds = 5;
    let buildInfo = $state({});
    let resultRetryTimeout;

    /**
     *
     * @param {number} queueItem
     * @returns {Promise<{_class: string, number: number, url: string}>}
     */
    const fetchBuildInfo = async function(queueItem) {
        try {
            let params = queryString.stringify({
                queueItem: queueItem,
            });
            const response = await fetch("/api/v1/jenkins/queue_info?" + params);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            let result = json.response.queueItem;
            if (!result.number) {
                resultRetryTimeout = setTimeout(async () => {
                    buildInfo = await fetchBuildInfo(queueItem);
                }, retrySeconds * 1000);
            }
            fetching = false;
            return result;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching build parameters.\nMessage: ${error.response.arguments[0]}`,
                    "BuildSuccess::fetchBuildQueue"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during parameter fetch",
                    "BuildSuccess::fetchBuildQueue"
                );
                console.log(error);
            }
            return error;
        }
    };

    onMount(async () => {
        buildInfo = await fetchBuildInfo(args.queueItem);
    });

    onDestroy(() => {
        if (resultRetryTimeout) {
            clearTimeout(resultRetryTimeout);
        }
    });
</script>

<div class="text-center p-2">
    {#if fetching}
        <div>
            <span class="spinner-border spinner-border-sm"></span> Receiving build info...
        </div>
    {:else}
        {#if buildInfo?.number}
            <div>
                Build #{buildInfo.number} started!
                <div class="mb-2">
                    <a href="{buildInfo.url}">Jenkins</a>
                </div>
                {#if args.isFirst}
                    <div>
                        This is a first build, which will require a re-run to actually start.
                        <div class="my-2 p-2">
                            <button class="w-100 btn btn-success" onclick={() => dispatch("exit", { firstBuildRestart: true, buildNumber: buildInfo.number })}>
                                <Fa icon={faArrowCircleRight} /> Start build #2
                            </button>
                        </div>
                    </div>
                {:else}
                    <div>
                        <div class="my-2 p-2">
                            <button class="w-100 btn btn-success" onclick={() => dispatch("exit", { firstBuildRestart: false, buildNumber: buildInfo.number })}>
                                <Fa icon={faArrowCircleRight} /> Exit and add the test to workspace
                            </button>
                        </div>
                    </div>
                {/if}
            </div>
        {:else}
        <div>
            Build is not started yet.
            <div>
                Reason: {buildInfo.why} (since: {timestampToISODate(new Date(buildInfo.inQueueSince), true)})
            </div>
            <div>
                Will re-check in {retrySeconds} seconds.
            </div>
            <div>
                <a href="{buildInfo.taskUrl}">Jenkins</a>
            </div>
        </div>
        {/if}
    {/if}
</div>
