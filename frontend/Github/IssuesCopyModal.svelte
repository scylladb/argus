<script lang="ts">
    import Fa from "svelte-fa";
    import {faClipboard, faCopy} from "@fortawesome/free-solid-svg-icons";

    import ModalWindow from "../Common/ModalWindow.svelte";
    import {faHtml5, faMarkdown} from "@fortawesome/free-brands-svg-icons";
    import {titleCase} from "../Common/TextUtils";
    import Color from "color";
    import { getAssignees, getAssigneesRich, getKey, getNumber, getTitle, getUrl, label2color, type Issue, type Label } from "./Issues.svelte";

    interface Props {
        sortedIssues?: Issue[][];
        currentPage?: number;
        selectedLabels?: Label[];
        btnClass?: string;
        children?: import('svelte').Snippet;
    }

    let {
        sortedIssues = [],
        currentPage = 0,
        selectedLabels = [],
        btnClass = "btn-success",
        children
    }: Props = $props();
    let issueCopy = $state(false);
    let issueTable: HTMLDivElement | null = $state(null);


    const copyIssueTableAsMarkdown = function () {
        const issues = sortedIssues[currentPage] ?? [];
        let issueFormattedList = issues
            .sort((a: Issue, b: Issue) => getNumber(a) - getNumber(b))
            .map((val: Issue) => `|${val.state ? `${val.state.toUpperCase()} ` : " "}|${getUrl(val)}|${val.state ? val.labels.map(v => v.name).join("\t") : ""}|${val.state && getAssignees(val) ? getAssignees(val).join(",") : ""}|`);
        navigator.clipboard.writeText(`Current Issues ${selectedLabels.length > 0 ? selectedLabels.map((label: Label) => `[${label.name}]`).join(" ") : ""}\n|State|Issue|Tags|Assignee|\n|---|---|---|---|\n${issueFormattedList.join("\n")}`);
    };

    const copyIssueTableAsText = function () {
        const issues = sortedIssues[currentPage] ?? [];

        const lines = issues.map((i: Issue) => ` * ${getUrl(i)} (${i?.state ?? ""}) [${getAssignees(i)[0] || "Nobody"}]`);
        navigator.clipboard.writeText(`Issues\n${lines.join("\n")}`);
    };

    const copyIssueTableAsHTML = async function () {
        const table = issueTable;

        const data = table?.innerHTML || "";
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
                <div bind:this={issueTable}>
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
                                    <a class="link-primary" href="{getUrl(issue)}">{getKey(issue)}</a>
                                </td>
                                <td style="border: solid 1px black">
                                    {getTitle(issue)}
                                </td>
                                <td style="border: solid 1px black">
                                    {#each issue.labels as label}
                                        {#if issue.subtype == "github"}
                                            <span style="text-decoration: underline; color: {Color(`#${label.color}`).darken(0.50)}">{label.name}</span><br>
                                        {:else}
                                            <span style="text-decoration: underline; color: {Color(`${label2color(label)}`).darken(0.50)}">{label.name}</span><br>
                                        {/if}
                                    {/each}
                                </td>
                                <td style="border: solid 1px black">
                                    {#each getAssigneesRich(issue) as assignee}
                                        <a href="{assignee.html_url}">@{assignee.login}</a><br>
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
