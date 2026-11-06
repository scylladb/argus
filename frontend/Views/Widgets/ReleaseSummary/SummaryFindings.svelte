<script lang="ts">
    import Fa from "svelte-fa";
    import { faLightbulb, faRobot } from "@fortawesome/free-solid-svg-icons";
    import type { User } from "../../../Common/UserTypes";
    import { userList } from "../../../Stores/UserlistSubscriber.js";
    import { updatedAgo } from "./summaryUtils";
    import type { SummaryFinding } from "./types";

    let { findings }: { findings: SummaryFinding[] } = $props();

    const users = $derived($userList as Record<string, User>);
    const author = (userId: string) => users[userId]?.full_name || users[userId]?.username || "Unknown user";
</script>

<section class="rounded bg-light-one shadow-sm p-2 mb-2" aria-label="Findings">
    <div class="d-flex align-items-center gap-2 mb-1 small fw-semibold">
        <Fa icon={faLightbulb} /> Findings
    </div>
    <ul class="list-unstyled d-flex flex-column gap-1 mb-0">
        {#each findings as finding (finding.id)}
            <li class="rounded bg-white shadow-sm px-2 py-1 small">
                <div class="finding-text">{finding.content}</div>
                <div class="text-body-secondary">
                    {author(finding.updated_by)} · {updatedAgo(finding.updated_at)}
                    {#if finding.source_node}<Fa icon={faRobot} title="Added from the chat" />{/if}
                </div>
            </li>
        {/each}
    </ul>
</section>

<style>
    .finding-text {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }
</style>
