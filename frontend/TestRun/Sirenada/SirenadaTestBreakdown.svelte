<script lang="ts">
    import { onMount } from "svelte";
    import sha1 from "js-sha1";
    import hljs from "highlight.js";
    import humanizeDuration from "humanize-duration";
    import { StatusSortPriority, TestStatus, StatusTableBackgroundCSSClassMap, StatusCSSClassMap, StatusBackgroundCSSClassMap } from "../../Common/TestStatus";
    import { titleCase, subUnderscores } from "../../Common/TextUtils";
    import Fa from "svelte-fa";
    import { faBucket, faCircleExclamation } from "@fortawesome/free-solid-svg-icons";
    import { Collapse } from "bootstrap";
    import { createScreenshotUrl } from "../../Common/RunUtils";

    let { testRun = {}, testInfo = {} } = $props();


    let resultsByBrowser = $state({});

    const normalize = function(val, max, min) {
        return (val - min) / (max - min);
    };

    const prepareResults = function(testRun) {
        return testRun.results.reduce((acc, val) => {
            let key = `${val.browser_type} [${val.cluster_type}]`;
            const classNameCollection = acc[key] ?? {};
            const classNameResults = classNameCollection[val.file_name] ?? [];
            classNameResults.push(val);
            classNameCollection[val.file_name] = classNameResults;
            acc[key] = classNameCollection;
            return acc;
        }, {});
    };

    const sortedStatusMap = function(resultList) {
        if (resultList.length == 0) return TestStatus.UNKNOWN;

        let statusMap = resultList
            .map(val => val.status)
            .reduce((acc, val) => {
                acc[val] = (acc[val] ?? 0) + 1;
                return acc;
            }, {});

        let sortedStatus = Object.entries(statusMap).sort(
            (a, b) => {
                let lhs = StatusSortPriority[a[0]] ?? -1;
                let rhs = StatusSortPriority[b[0]] ?? -1;
                return lhs - rhs;
            }
        );
        return sortedStatus;
    };

    const calculateStatus = function(resultList) {
        return sortedStatusMap(resultList)[0];
    };

    const findTestWithS3Bucket = function(testsByClass) {
        const flattenedTests = Object
            .values(testsByClass)
            .reduce((acc, val) => [...acc, ...val], []);
        return flattenedTests.filter(v => v.s3_folder_id)[0];
    };

    const expandAllFailures = function(hash) {
        let failedCollapses = document.querySelectorAll(`.has-errors-${hash}`);
        failedCollapses.forEach(v => new Collapse(v).show());
    };

    onMount(() => {
        resultsByBrowser = prepareResults(testRun);
    });
</script>
<div class="p-3">
<div
        class="flex-fill d-flex shadow-sm overflow-hidden border rounded cursor-question"
        title="Total: {testRun.results.length}"
    >
        {#each sortedStatusMap(testRun.results) as status_map}
                <div
                    class="d-flex align-items-center justify-content-center flex-fill {StatusBackgroundCSSClassMap[status_map[0]]}"
                    style="width: {Math.max(Math.round(normalize(status_map[1], testRun.results.length, 0) * 100), 10)}%"
                    title="{subUnderscores(titleCase(status_map[0]))} ({status_map[1]})"
                >
                    <div class="p-1 text-small text-light text-outline">
                            {status_map[1]}
                    </div>
                </div>
        {/each}
    </div>
</div>
<div class="p-2">
    {#each Object.entries(resultsByBrowser) as [browserType, testsByClass], idx (browserType)}
        {@const firstResult = Object.values(testsByClass)[0][0]}
        {@const failingTest = findTestWithS3Bucket(testsByClass)}
        {@const tableHash = sha1(`${browserType}-${firstResult.cluster_type}`).substring(0, 10)}
        <div class="rounded p-2 m-2 bg-light-one">
            <div class="mb-2 bg-white rounded p-2 d-flex align-items-center">
                <h6 class="m-0">{browserType}</h6>
                {#if failingTest}
                    <div class="ms-auto">
                        <a
                            class="btn btn-sm btn-dark"
                            href="https://s3.console.aws.amazon.com/s3/buckets/sirenada-results?prefix={failingTest.s3_folder_id}/sirenada-{failingTest.sirenada_test_id}/"
                            target="_blank"
                        >
                            <Fa icon={faBucket}/> S3 Bucket
                        </a>
                    </div>
                    <div>
                        <button class="ms-2 btn btn-sm btn-danger" onclick={() => expandAllFailures(tableHash)}>
                            <Fa icon={faCircleExclamation}/> Expand all failures
                        </button>
                    </div>
                {/if}
            </div>
            <table class="table table-hover bg-white rounded">
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {#each Object.entries(testsByClass) as [fileName, resultList], idx (fileName)}
                        {@const status = calculateStatus(resultList ?? [])}
                        {@const blockHash = sha1(`testResults-${testRun.id}-${browserType}-${fileName}`).substring(0, 10)}
                        {@const hasErrors = resultList.filter(val => ["failed", "error", "aborted"].includes(val.status)).length > 0}
                        <tr>
                            <!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
                            <td
                                data-bs-toggle="collapse"
                                data-bs-target="#result-{blockHash}"
                            >
                                {fileName}
                            </td>
                            {#if hasErrors}
                                <td class="{StatusTableBackgroundCSSClassMap[status[0]]}">{titleCase(status[0])} ({status[1]} tests)</td>
                            {:else}
                                <td class="{StatusTableBackgroundCSSClassMap[status[0]]}">{titleCase(status[0])}</td>
                            {/if}
                        </tr>
                        <tr class="collapse bg-white {hasErrors ? `has-errors-${tableHash}` : ""}" id="result-{blockHash}">
                            <td colspan="2" class="table-active">
                                <div class="bg-white">
                                    <table class="table table-hover rounded overflow-hidden">
                                        <thead>
                                            <tr>
                                                <th>Test</th>
                                                <th>Class Name</th>
                                                <th>Duration</th>
                                                <th>Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each resultList as result}
                                                {@const resultHash = sha1(`testResults-${testRun.id}-${browserType}-${fileName}-${result.test_name}`).substring(0, 10)}
                                                {@const failed = ["failed", "error", "aborted"].includes(result.status.toLowerCase())}
                                                <tr class="">
                                                    <td
                                                        data-bs-toggle="{result.status != "passed" ? "collapse" : ""}"
                                                        data-bs-target="#test-{resultHash}"
                                                    >
                                                        {result.test_name}
                                                    </td>
                                                    <td>{result.class_name.split(".").at(-1)}</td>
                                                    <td>{humanizeDuration(result.duration, { maxDecimalPoints: 4 })}</td>
                                                    <td class="{StatusTableBackgroundCSSClassMap[result.status]}">{titleCase(result.status)}</td>
                                                </tr>
                                                {#if result.status != "passed"}
                                                    <tr class="collapse {failed ? `has-errors-${tableHash}` : ""}" id="test-{resultHash}">
                                                        <td colspan="4" class="">
                                                            <div class="bg-white d-flex flex-column p-2 rounded">
                                                                <div class="mb-2">
                                                                    <span class="fw-bold">Status:</span> <span class="{StatusCSSClassMap[result.status]}">{titleCase(result.status)}</span>
                                                                </div>
                                                                <div class="mb-2">
                                                                    <span class="fw-bold">Class name:</span> {result.class_name}
                                                                </div>
                                                                <div class="mb-2">
                                                                    <span class="fw-bold">Source File:</span> {result.file_name}
                                                                </div>
                                                                <div class="mb-2">
                                                                    <span class="fw-bold">Requests:</span> <a href="{result.requests_file}">Link</a>
                                                                </div>
                                                                <div class="mb-2 p-2">
                                                                    <h6>Screenshot</h6>
                                                                    <div>
                                                                        <img src="{createScreenshotUrl(testInfo.test.plugin_name, testRun.id, result.screenshot_file)}" alt="Screenshot" style="width: 256px;">
                                                                    </div>
                                                                </div>
                                                                {#if result.message}
                                                                    <div class="mb-2 p-2">
                                                                        <h6>Message</h6>
                                                                        <div class="bg-light-one rounded">
                                                                            <pre class="p-2 hljs bg-light-one language-python" style="white-space: pre-wrap">{@html hljs.highlight(result.message, {language: "python"}).value}</pre>
                                                                        </div>
                                                                    </div>
                                                                {/if}
                                                                {#if result.stack_trace}
                                                                    <div class="mb-2 p-2">
                                                                        <h6>Stack Trace</h6>
                                                                        <div class="bg-light-one rounded p-2">
                                                                            <pre style="white-space: pre-wrap">{@html hljs.highlight(result.stack_trace, {language: "python"}).value}</pre>
                                                                        </div>
                                                                    </div>
                                                                {/if}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                {/if}
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </td>
                        </tr>
                    {/each}
                </tbody>
            </table>
            <div>
            </div>
        </div>
    {/each}
</div>

<style>

</style>
