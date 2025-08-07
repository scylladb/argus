<!-- @migration-task Error while migrating Svelte code: `<th>` cannot be a child of `<thead>`. `<thead>` only allows these children: `<tr>`, `<style>`, `<script>`, `<template>`. The browser will 'repair' the HTML (by moving, removing, or inserting elements) which breaks Svelte's assumptions about the structure of your components.
https://svelte.dev/e/node_invalid_placement -->
<script lang="ts">
    import humanize from "humanize-duration";
    import Fa from "svelte-fa";
    import { faCircle, faBoxes } from "@fortawesome/free-solid-svg-icons";
    import type { TestSuite } from "../Common/DriverMatrixTypes";
    export let suites: TestSuite[];

</script>


{#each suites as suite}
    <div>
        <h4 class="d-flex align-items-center">
            <div>{suite.name}</div>
            <div class="ms-2 p-1 p-help" title="Total">
                <Fa size="sm" icon={faBoxes}/> {suite.tests_total}
            </div>
            <div class="ms-2 p-1 p-help" title="Passed">
                <Fa size="sm" class="text-success" icon={faCircle}/> {suite.passed}
            </div>
            <div class="ms-2 p-1 p-help" title="Failed">
                <Fa size="sm" class="text-danger" icon={faCircle}/> {suite.failures}
            </div>
            <div class="ms-2 p-1 p-help" title="Skipped">
                <Fa size="sm" class="text-secondary" icon={faCircle}/> {suite.skipped}
            </div>
            <div class="ms-2 p-1 p-help" title="Errors">
                <Fa size="sm" class="text-warning" icon={faCircle}/> {suite.errors}
            </div>
            <div class="ms-2 p-1 p-help" title="Disabled">
                <Fa size="sm" class="text-dark" icon={faCircle}/> {suite.disabled}
            </div>
        </h4>
        <table class="table table-hover table-bordered border border-dark">
            <thead>
                <th>Name</th>
                <th>Status</th>
                <th>Time taken</th>
                <th>Message</th>
                <th>Classname</th>
            </thead>
            <tbody>
                {#each suite.cases as cs}
                    <tr class="border border-dark bg-{cs.status}">
                        <td class="border border-dark">{cs.name}</td>
                        <td class="border border-dark">{cs.status}</td>
                        <td class="border border-dark">
                            {humanize(cs.time, {
                                largest: 2,
                                maxDecimalPoints: 2,
                            })}
                        </td>
                        <td class="border border-dark text-truncate overflow-hidden" style="max-width: 8rem;" title={cs.message ?? ""}>{cs.message ?? ""}</td>
                        <td class="border border-dark text-truncate" style="max-width: 8rem;" title={cs.classname}>{cs.classname}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/each}

<style>
    .p-help {
        cursor: help;
    }
    .bg-passed {
        background-color: rgb(165, 253, 165);
    }
    .bg-failure {
        background-color: rgb(255, 147, 147);
    }
    .bg-skipped {
        background-color: rgb(223, 223, 223);
    }
    .bg-disabled {
        background-color: rgb(147, 147, 147);
    }
    .bg-error {
        background-color: rgb(237, 138, 240);
    }
</style>
