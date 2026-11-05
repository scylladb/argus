<script lang="ts">
    import Fa from "svelte-fa";
    import { faCompress, faRobot } from "@fortawesome/free-solid-svg-icons";
    import { percent } from "./chatFormat";
    import type { ChatModelInfo, ContextStats } from "./types";

    interface Props {
        context: ContextStats;
        model: ChatModelInfo | null;
        busy: boolean;
        empty: boolean;
        onCompact: () => void;
    }

    let { context, model, busy, empty, onCompact }: Props = $props();

    const share = $derived(percent(context.used, context.window));
    const tone = $derived(share >= 85 ? "bg-danger" : share >= 60 ? "bg-warning" : "bg-success");
</script>

{#if model}
    <section class="rounded bg-white shadow-sm p-2 small">
        <header class="text-body-secondary mb-1"><Fa icon={faRobot} /> Model</header>
        <div class="fw-semibold text-break">{model.model}</div>
        <div class="text-body-secondary">{model.connection}{model.tools ? "" : " · answers without tools"}</div>
    </section>
{/if}

<section class="rounded bg-white shadow-sm p-2 small">
    <header class="d-flex justify-content-between mb-1">
        <span class="text-body-secondary">Context</span>
        <span>{context.used.toLocaleString()} / {context.window.toLocaleString()} tokens</span>
    </header>
    <div class="progress" role="progressbar" aria-label="Context used" aria-valuenow={share}
         aria-valuemin={0} aria-valuemax={100}>
        <div class="progress-bar {tone}" style="width: {share}%">{share}%</div>
    </div>
    <div class="text-body-secondary mt-1">
        {context.messages_since_compaction} message{context.messages_since_compaction === 1 ? "" : "s"} since the last
        compaction{#if context.estimated_tokens}, about {context.estimated_tokens.toLocaleString()} tokens
            estimated{/if}.
    </div>
</section>

<section class="rounded bg-white shadow-sm p-2 small">
    <p class="text-body-secondary mb-2">
        Summarize conversation to free up context. Can be undone on history page.
    </p>
    <button type="button" class="btn btn-sm btn-primary" disabled={busy || empty} onclick={onCompact}>
        <Fa icon={faCompress} /> Compact context
    </button>
</section>
