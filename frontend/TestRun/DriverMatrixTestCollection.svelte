<script lang="ts">
    import Fa from "svelte-fa";
    import { faCircle, faBoxes, faWarning, faExclamationCircle } from "@fortawesome/free-solid-svg-icons";
    import DriverMatrixBreakdown from "./DriverMatrixBreakdown.svelte";
    import type { TestCollection } from "../Common/DriverMatrixTypes";
    interface Props {
        collections: TestCollection[];
        testId: string;
    }

    let { collections, testId }: Props = $props();

    const calculateCollectionStatus = function(collection: TestCollection): boolean {
        return collection.failures > 0 || collection.errors > 0;
    };

    const statusFilter = {
        failure: true,
        error: true,
    };
</script>

<div class="accordion accordion-flush">
    {#each collections as collection, idx}
    {@const isFailed = calculateCollectionStatus(collection)}
        <div class="accordion-item">
            <h2 class="accordion-header" id="headingTestCollection-{testId}-{idx}">
                <button
                    class="accordion-button collapsed collection-{isFailed ? "danger" : "success"}"
                    type="button"
                    data-bs-toggle="collapse"
                    data-bs-target="#collapseTestCollection-{testId}-{idx}"
                >
                    <div class="d-flex align-items-center flex-fill">
                        <div class="ms-1">{collection.name}</div>
                        {#if isFailed}
                        {@const failureCount = collection.failures + collection.errors}
                            <div class="ms-auto me-2 rounded">
                                <Fa color="#fab73a" icon={faExclamationCircle}/>
                                {failureCount} test{failureCount > 1 ? "s" : ""} failed
                            </div>
                        {/if}
                    </div>
                </button>
            </h2>
            <div id="collapseTestCollection-{testId}-{idx}" class="accordion-collapse collapse">
                <div class="accordion-body" >
                    {#if collection.failure_message}
                        <div>
                            <pre class="rounded p-2 bg-light-one" style="white-space: pre-wrap;">{collection.failure_message}</pre>
                        </div>
                    {:else}
                        <DriverMatrixBreakdown suites={collection.suites}/>
                    {/if}
                </div>
            </div>
        </div>
    {/each}
</div>


<style>
    .collection-success {
        background-color: rgba(173, 249, 172, 0.5);
    }

    .collection-danger {
        background-color: rgba(255, 175, 175, 0.5);
    }
</style>
