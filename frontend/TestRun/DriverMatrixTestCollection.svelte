<script lang="ts">
    import Fa from "svelte-fa";
    import { faCircle, faBoxes } from "@fortawesome/free-solid-svg-icons";
    import type { TestCollection } from "../Common/DriverMatrixTypes";
    import DriverMatrixTestSuites from "./DriverMatrixTestSuites.svelte";
    export let testCollection: TestCollection[];
    export let testId: string;

    const calculateCollectionStatus = function(collection: TestCollection): string {
        return collection.failures > 0 || collection.errors > 0 ? "danger" : "success";
    };
</script>

<div class="accordion" id="testCollectionAccordion">
    {#each testCollection as testCol, idx}
        <div class="accordion-item">
            <h2 class="accordion-header" id="headingTestCollection-{testId}-{idx}">
                <button
                    class="accordion-button collapsed collection-{calculateCollectionStatus(testCol)}"
                    type="button"
                    data-bs-toggle="collapse"
                    data-bs-target="#collapseTestCollection-{testId}-{idx}"
                >
                    <div class="d-flex align-items-center flex-fill">
                        <div class="ms-1">{testCol.name}</div>
                        <div class="ms-auto p-1 p-help" title="Total">
                            <Fa size="sm" icon={faBoxes}/> {testCol.tests_total}
                        </div>
                        <div class="ms-2 p-1 p-help" title="Passed">
                            <Fa size="sm" class="text-success" icon={faCircle}/> {testCol.passed}
                        </div>
                        <div class="ms-2 p-1 p-help" title="Failed">
                            <Fa size="sm" class="text-danger" icon={faCircle}/> {testCol.failures}
                        </div>
                        <div class="ms-2 p-1 p-help" title="Skipped">
                            <Fa size="sm" class="text-secondary" icon={faCircle}/> {testCol.skipped}
                        </div>
                        <div class="ms-2 p-1 p-help" title="Errors">
                            <Fa size="sm" class="text-warning" icon={faCircle}/> {testCol.errors}
                        </div>
                        <div class="ms-2 p-1 p-help" title="Disabled">
                            <Fa size="sm" class="text-dark" icon={faCircle}/> {testCol.disabled}
                        </div>
                    </div>
                </button>
            </h2>
            <div id="collapseTestCollection-{testId}-{idx}" class="accordion-collapse collapse" data-bs-parent="#testCollectionAccordion">
                <div class="accordion-body" >
                    <DriverMatrixTestSuites suites={testCol.suites} />
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
