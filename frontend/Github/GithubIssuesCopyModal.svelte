<script lang="ts">
    import Fa from "svelte-fa";
    import {faClipboard, faCopy} from "@fortawesome/free-solid-svg-icons";

    import ModalWindow from "../Common/ModalWindow.svelte";
    import {faHtml5, faMarkdown} from "@fortawesome/free-brands-svg-icons";
    import {titleCase} from "../Common/TextUtils";
    import Color from "color";

    interface Props {
        sortedIssues?: any;
        currentPage?: number;
        selectedLabels?: any;
        btnClass?: string;
        children?: import('svelte').Snippet;
    }

    let {
        sortedIssues = {},
        currentPage = 0,
        selectedLabels = [],
        btnClass = "btn-success",
        children
    }: Props = $props();
    let issueCopy = $state(false);


    const copyIssueTableAsMarkdown = function () {
        const issues = sortedIssues[currentPage] ?? [];
        let issueFormattedList = issues
            .sort((a, b) => a.number - b.number)
            .map(val => `|${val.state ? `${val.state.state.toUpperCase()} ` : " "}|${val.url}|${val.state ? val.state.labels.map(v => v.name).join("\t") : ""}|${val.state && val.assignees ? val.assignees.map(v => v.login).join(",") : ""}|`);
        navigator.clipboard.writeText(`Current Issues ${selectedLabels.length > 0 ? selectedLabels.map(label => `[${label.name}]`).join(" ") : ""}\n|State|Issue|Tags|Assignee|\n|---|---|---|---|\n${issueFormattedList.join("\n")}`);
    };

    const copyIssueTableAsText = function () {
        const issues = sortedIssues[currentPage] ?? [];

        const lines = issues.map(i => ` * ${i.url} (${i?.state?.state ?? ""}) [${i?.state?.assignee?.login ?? "Nobody"}]`);
        navigator.clipboard.writeText(`Issues\n${lines.join("\n")}`);
    };

    const copyIssueTableAsHTML = async function () {
        const table = document.querySelector("div#modalTableIssueView");

        const data = table.innerHTML;
        // Baseline: June 2024
        // eslint-disable-next-line no-undef
        const clipboardItem = new ClipboardItem({
            "text/html": new Blob([data], {type: "text/html"}),
            "text/plain": new Blob([data], {type: "text/plain"})
        });

        await navigator.clipboard.write([clipboardItem]);
    };
</script>

<button class="btn {btnClass}" onclick={() => issueCopy = true}>
    {@render children?.()}
</button>

{#if issueCopy}
    <ModalWindow on:modalClose={() => issueCopy = false}>
        {#snippet title()}
                <div class="" >
                Issues
            </div>
            {/snippet}
        {#snippet body()}
                <div class="" >
                <div class="mb-2 text-end">
                    <button class="btn btn-outline-primary" onclick={copyIssueTableAsHTML}>
                        <Fa icon={faHtml5}/>
                        Copy as HTML
                    </button>
                    <button class="btn btn-outline-primary" onclick={copyIssueTableAsMarkdown}>
                        <Fa icon={faMarkdown}/>
                        Copy as Markdown
                    </button>
                    <button class="btn btn-outline-primary" onclick={copyIssueTableAsText}>
                        <Fa icon={faClipboard}/>
                        Copy as Text
                    </button>
                </div>
                <div id="modalTableIssueView">
                    <table class="table" style="border: solid 1px black">
                        <thead>
                            <tr>
                                <th style="border: solid 1px black">State</th>
                                <th style="border: solid 1px black">Issue</th>
                                <th style="border: solid 1px black">Title</th>
                                <th style="border: solid 1px black">Tags</th>
                                <th style="border: solid 1px black">Assignee</th>
                            </tr>
                        </thead>
                        <tbody>
                        {#each sortedIssues[currentPage] ?? [] as issue (issue.id)}
                            <tr>
                                <td style="border: solid 1px black">{titleCase(issue?.state)}</td>
                                <td style="border: solid 1px black">
                                    <a class="link-primary" href="{issue.url}">{issue.owner}/{issue.repo}#{issue.number}</a>
                                </td>
                                <td style="border: solid 1px black">
                                    {issue.title}
                                </td>
                                <td style="border: solid 1px black">
                                    {#each issue.labels as label}
                                        <span style="text-decoration: underline; color: {Color(`#${label.color}`).darken(0.50)}">{label.name}</span><br>
                                    {/each}
                                </td>
                                <td style="border: solid 1px black">
                                    {#each issue.assignees as assignee}
                                        <a href="{assignee.html_url}">@{assignee.login}</a>
                                    {:else}
                                        None
                                    {/each}
                                </td>
                            </tr>
                        {/each}
                        </tbody>
                    </table>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}
