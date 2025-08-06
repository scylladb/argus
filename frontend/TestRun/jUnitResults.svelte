<script lang="ts">
    import { titleCase } from "../Common/TextUtils";
    import JUnitChart from "./jUnitChart.svelte";

    let { results } = $props();

    const statusInfo = {
        failure: {
            show: true,
            testCount: 0,
            class: "bg-danger",
        },
        error: {
            show: true,
            testCount: 0,
            class: "bg-warning",
        },
        passed: {
            show: false,
            testCount: 0,
            class: "bg-success",
        },
        skipped: {
            show: false,
            testCount: 0,
            class: "bg-secondary",
        },
        disabled: {
            show: false,
            testCount: 0,
            class: "bg-dark",
        },
    };
    const parsejUnitXml = function(raw_content) {
        let parser = new DOMParser();

        let doc = parser.parseFromString(raw_content, "text/xml");
        let cases = Array
            .from(doc.querySelectorAll("testcase"))
            .map(raw_case => {
                let statusNode = raw_case.childNodes.length > 0 ? Array.from(raw_case.childNodes).filter(v => v.nodeName !== "#text" && v.nodeName !== "system-out" && v.nodeName !== "system-err")[0] : undefined;
                return {
                    name: raw_case.attributes.getNamedItem("name").textContent,
                    class: raw_case.attributes.getNamedItem("classname").textContent,
                    time: new Number(raw_case.attributes.getNamedItem("time").textContent),
                    status: statusNode ? statusNode.nodeName : "passed",
                    message: statusNode ? statusNode.textContent : "",
                };
            });

        return cases;
    };


</script>

{#each results as res (res.file_name)}
    {@const parsed = parsejUnitXml(res.report)}
    <div class="p-2 mb-2">
        <div class="fw-bold mb-2 border-bottom d-block w-25 pb-2">{titleCase(res.file_name)}</div>
        <div>
            <JUnitChart results={parsed} />
        </div>
        <div class="p-2 rounded bg-light-one">
            {#each parsed as testCase (testCase.name, testCase.class)}
                <div class="bg-white rounded mb-2">
                    <div class="d-flex p-2 align-items-center">
                        <div>
                            {testCase.name}
                            <div class="text-small text-secondary">{testCase.class}</div>
                        </div>
                        <div class="ms-auto d-inline rounded p-2 text-white {statusInfo[testCase.status]?.class ?? statusInfo.disabled.class}">
                            {testCase.status.toUpperCase()}
                        </div>
                    </div>
                    {#if testCase.message}
                        <div class="p-2">
                            <pre class="bg-light-one rounded m-0 p-2 case-message">{testCase.message}</pre>
                        </div>
                    {/if}
                </div>
            {/each}
        </div>
    </div>
{/each}

<style>
    .case-message {
        white-space: pre-wrap
    }
</style>
