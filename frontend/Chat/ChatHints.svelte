<script lang="ts">
    import Fa from "svelte-fa";
    import { faArrowUpRightFromSquare } from "@fortawesome/free-solid-svg-icons";
    import { DOCS_URL, EXAMPLE_GROUPS } from "./chatExamples";

    interface Props {
        onpick: (text: string) => void;
        compact?: boolean;
    }

    let { onpick, compact = false }: Props = $props();
</script>

<div class="d-flex flex-column gap-2" class:text-start={compact}>
    {#each EXAMPLE_GROUPS as group (group.title)}
        <section aria-label={group.title}>
            <h3 class="h6 small fw-semibold mb-1">{group.title}</h3>
            <div class="d-flex flex-wrap gap-1" class:justify-content-center={!compact}>
                {#each group.examples as example (example)}
                    <button type="button" class="btn btn-sm btn-outline-secondary text-start example"
                            onclick={() => onpick(example)}>
                        {example}
                    </button>
                {/each}
            </div>
        </section>
    {/each}
    <p class="small text-body-secondary mb-0">
        A click puts the example in the question box; replace the parts in &lt;angle brackets&gt;. Starting tests,
        editing a plan, linking an issue and posting a comment only propose a card: nothing changes until someone
        confirms it with <strong>Run</strong>, <strong>Apply</strong> or <strong>Queue</strong>.
        <strong>Auto mode</strong> confirms the cards of your own questions at once.
    </p>
    <a class="small" href={DOCS_URL} target="_blank" rel="noopener noreferrer">
        Everything the chat can do <Fa icon={faArrowUpRightFromSquare} size="xs" />
    </a>
</div>

<style>
    .example {
        white-space: normal;
    }
</style>
