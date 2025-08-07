<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import Fa from "svelte-fa";
    import {faBan, faChartLine, faPlus, faRefresh, faTimes} from "@fortawesome/free-solid-svg-icons";
    import { extractBuildNumber } from "../Common/RunUtils";
    import { StatusButtonCSSClassMap } from "../Common/TestStatus";
    import { Modal } from "bootstrap";
    import { sendMessage } from "../Stores/AlertStore";

    let {
        testInfo = {},
        testId,
        runs = [],
        clickedTestRuns = {}
    } = $props();

    const dispatch = createEventDispatcher();
    let sticky = $state(false);
    let header = $state();
    let ignoreReason = $state("");
    let modal = $state();
    let showGraphButton = $state(false);

    const showGraphsButtonIfResultsExist = async function () {
        try {
            let res = await fetch(`/api/v1/test-results?testId=${testId}`, {
                method: "HEAD"
            });
            if (res.status === 200) {
                showGraphButton = true;
            }
        } catch (error) {
            console.error("Error while finding if results are present:", error);
        }
    };

    onMount(() => {
        showGraphsButtonIfResultsExist();
        let observer = new IntersectionObserver((entries) => {
            let entry = entries[0];
            if (!entry) return;
            if (entry.intersectionRatio == 0 && !entry.isIntersecting) {
                sticky = true;
            } else {
                sticky = false;
            }
        }, {
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });
        observer.observe(header);
    });

</script>

<div class="h-small" bind:this={header}></div>
<div class="p-2 mb-2 bg-main" class:sticky={sticky} class:border={sticky} class:shadow={sticky}>
    {#if sticky}
        <div class="mb-1 p-1">
            {testInfo.test.name} ({testInfo.release.name}/{testInfo.group.name})
        </div>
    {/if}
    {#if showGraphButton}
        <div class="me-2 mb-2 d-inline-block">
            <button
                    class="btn btn-light"
                    onclick={() => {
                dispatch("showGraph");
            }}
            >
                <Fa icon={faChartLine}/>
            </button>
        </div>
    {/if}
    {#each runs as run (run.id)}
        <div class="me-2 mb-2 d-inline-block">
            <div class="btn-group">
                <button
                    class:active={clickedTestRuns[run.id]}
                    class="btn {StatusButtonCSSClassMap[run.status]}"
                    type="button"
                    onclick={() => dispatch("runClick", { runId: run.id })}
                >
                    #{extractBuildNumber(run)}
                </button>
                {#if clickedTestRuns[run.id]}
                    <button
                        class="btn border-start-dark {StatusButtonCSSClassMap[run.status]}"
                        data-run-id={run.id}
                        onclick={() => {
                            dispatch("closeRun", { id: run.id });
                        }}
                    >
                        <Fa icon={faTimes} />
                    </button>
                {/if}
            </div>
        </div>
    {/each}
    <div class="me-2 mb-2 d-inline-block">
        <button
            class="btn btn-light"
            onclick={() => {
                dispatch("increaseLimit");
            }}
        >
            <Fa icon={faPlus}/>
        </button>
    </div>
    <div class="me-2 mb-2 d-inline-block">
        <button
            class="btn btn-light"
            title="Ignore failed runs"
            onclick={() => {
                modal = new Modal(`#modalIgnoreRuns-${testInfo.test.id}`);
                modal.show();
            }}
        >
            <Fa icon={faBan}/>
        </button>
    </div>
    <div class="d-inline-block">
        <button
            class="btn btn-light"
            onclick={() => dispatch("fetchNewRuns")}
            title="Fetch Runs"
        >
            <Fa icon={faRefresh}/>
        </button>
    </div>
</div>

<div class="modal" id="modalIgnoreRuns-{testInfo.test.id}" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Ignore runs</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p>You have chosen to ignore failed and not investigated runs for {testInfo.test.name}.
                    To finish the process, please provide a reason</p>
                <textarea rows="10" bind:value={ignoreReason} style="width: 100%"></textarea>
            </div>
            <div class="modal-footer">
                <button
                    type="button"
                    class="btn btn-secondary"
                    onclick={() => {
                        modal.hide();
                        ignoreReason = "";
                    }}
                >
                    Cancel
                </button>
                <button
                    type="button"
                    class="btn btn-danger"
                    onclick={() => {
                        if (!ignoreReason) {
                            sendMessage("error", "Ignore reason cannot be empty", "TestRuns::component");
                            return;
                        }
                        modal.hide();

                        dispatch("ignoreRuns", {
                            testId: testInfo.test.id,
                            reason: ignoreReason,
                        });
                        ignoreReason = "";
                    }}
                >
                    Submit
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .border-start-dark {
        border-left: 1px solid rgb(81, 81, 81);
    }
    .active::before {
        font-family: "Noto Sans Packaged", "Noto Sans", sans-serif;
        content: "● ";
    }

    .sticky {
        position: sticky;
        top: 12px;
        z-index: 999;
        margin: 1em;
        border-radius: 4px;
    }

    .h-small {
        height: 4px;
    }
</style>
