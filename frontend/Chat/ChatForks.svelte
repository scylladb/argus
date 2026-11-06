<script lang="ts">
    import Fa from "svelte-fa";
    import { faCodeBranch } from "@fortawesome/free-solid-svg-icons";
    import type { User } from "../Common/UserTypes";
    import { ago, displayName, preview } from "./chatFormat";
    import type { Branch } from "./chatTree";

    interface Props {
        branches: Branch[];
        users: Record<string, User>;
        busy: boolean;
        onSwitch: (leaf: string) => Promise<void>;
    }

    let { branches, users, busy, onSwitch }: Props = $props();

    let switching = $state<string | null>(null);

    const switchTo = async (leaf: string) => {
        switching = leaf;
        try {
            await onSwitch(leaf);
        } finally {
            switching = null;
        }
    };
</script>

{#if branches.length <= 1}
    <div class="small text-body-secondary px-1">
        One branch so far. <Fa icon={faCodeBranch} /> Fork after an answer to try another way from there.
    </div>
{:else}
    <div class="small text-body-secondary px-1">Switching changes the branch for everyone in this chat.</div>
    {#each branches as branch (branch.leaf.node)}
        <article class="card-block rounded bg-white shadow-sm p-2 small" class:current={branch.current}>
            <div class="d-flex align-items-center gap-2">
                <Fa icon={faCodeBranch} />
                <span class="fw-semibold text-truncate">
                    {branch.lastQuestion ? preview(branch.lastQuestion.content, 80) : "No questions"}
                </span>
                {#if branch.current}
                    <span class="badge text-bg-primary ms-auto">Current</span>
                {:else}
                    <button type="button" class="btn btn-sm btn-link p-0 ms-auto text-decoration-none"
                            disabled={busy || switching !== null} onclick={() => switchTo(branch.leaf.node)}>
                        {switching === branch.leaf.node ? "Switching…" : "Switch"}
                    </button>
                {/if}
            </div>
            {#if branch.divergence}
                <div class="text-body-secondary mt-1">
                    {#if branch.divergence.kind === "question"}
                        Asks instead: {preview(branch.divergence.node.content, 100)}
                    {:else}
                        Another answer to: {preview(branch.divergence.question?.content ?? "", 100)}
                    {/if}
                </div>
            {/if}
            <div class="text-body-secondary mt-1">
                {branch.questions} question{branch.questions === 1 ? "" : "s"} ·
                {#if branch.lastQuestion}last by {displayName(branch.lastQuestion.user_id, users)}{/if}
                {ago(branch.leaf.created_at)}
            </div>
        </article>
    {/each}
{/if}

<style>
    .current {
        border-left: 3px solid var(--bs-primary);
    }
</style>
