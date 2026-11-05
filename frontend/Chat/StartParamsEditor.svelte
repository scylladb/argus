<script lang="ts">
    import Fa from "svelte-fa";
    import { faRotateLeft } from "@fortawesome/free-solid-svg-icons";
    import type { JobField, ProposedTest } from "./types";

    interface Props {
        test: ProposedTest;
        onSave: (testId: string, overrides: Record<string, string>) => Promise<string | null>;
        onClose: () => void;
    }

    let { test, onSave, onClose }: Props = $props();

    const GROUP_NAMES: Record<string, string> = {
        environment: "Environment",
        scylla: "Scylla installation",
        test: "Test configuration",
        post_test: "After the test",
        reporting: "Reporting",
        other: "Other parameters",
    };

    let draft = $state<Record<string, string>>({});
    let filter = $state("");
    let saving = $state(false);
    let error = $state("");

    $effect.pre(() => {
        draft = { ...test.overrides };
    });

    const fields = $derived<JobField[]>(
        test.fields ??
            Object.entries(test.params).map(([name, value]) => ({ name, value, group: "other" })),
    );
    const shown = $derived(
        fields.filter((field) => !filter.trim() || field.name.toLowerCase().includes(filter.trim().toLowerCase())),
    );
    const groups = $derived.by(() => {
        const byGroup: Record<string, JobField[]> = {};
        for (const field of shown) (byGroup[field.group] ??= []).push(field);
        return Object.entries(byGroup);
    });
    const changed = $derived(JSON.stringify(draft) !== JSON.stringify(test.overrides));

    const valueOf = (field: JobField) => draft[field.name] ?? test.params[field.name] ?? field.value ?? "";

    const setValue = (field: JobField, value: string) => {
        draft = { ...draft, [field.name]: value };
    };

    const reset = (name: string) => {
        const { [name]: _, ...rest } = draft;
        draft = rest;
    };

    const save = async () => {
        saving = true;
        error = "";
        try {
            const failure = await onSave(test.test_id, draft);
            if (failure) {
                error = failure;
            } else {
                onClose();
            }
        } finally {
            saving = false;
        }
    };
</script>

<div class="editor rounded bg-light-one p-2 mt-1">
    <div class="d-flex align-items-center gap-2 mb-2">
        <input class="form-control form-control-sm filter" placeholder="Filter parameters" aria-label="Filter parameters"
               bind:value={filter} />
        <span class="small text-body-secondary text-nowrap">
            From {test.seed === "defaults" ? "the job's defaults" :
                test.seed === "build" ? `build #${test.build_number}` : "the last build"}
        </span>
    </div>
    <div class="fields">
        {#each groups as [group, entries] (group)}
            <div class="small fw-semibold text-body-secondary mt-1">{GROUP_NAMES[group] ?? group}</div>
            {#each entries as field (field.name)}
                {@const id = `param-${test.test_id}-${field.name}`}
                <div class="row g-1 mx-0 align-items-center py-1" class:overridden={field.name in draft}>
                    <label class="col-5 small font-monospace text-break" for={id} title={field.description ?? ""}>
                        {field.name}
                    </label>
                    <div class="col-6">
                        {#if field.choices?.length}
                            <select {id} class="form-select form-select-sm" value={valueOf(field)}
                                    onchange={(event) => setValue(field, (event.currentTarget as HTMLSelectElement).value)}>
                                {#if !field.choices.includes(valueOf(field))}
                                    <option value={valueOf(field)}>{valueOf(field) || "(empty)"}</option>
                                {/if}
                                {#each field.choices as choice (choice)}
                                    <option value={choice}>{choice}</option>
                                {/each}
                            </select>
                        {:else}
                            <input {id} class="form-control form-control-sm font-monospace" value={valueOf(field)}
                                   oninput={(event) => setValue(field, (event.currentTarget as HTMLInputElement).value)} />
                        {/if}
                    </div>
                    <div class="col-1 text-end">
                        {#if field.name in draft}
                            <button type="button" class="btn btn-sm btn-link text-body-secondary p-0"
                                    title="Back to the seed's value" aria-label="Reset {field.name}"
                                    onclick={() => reset(field.name)}>
                                <Fa icon={faRotateLeft} />
                            </button>
                        {/if}
                    </div>
                </div>
            {/each}
        {/each}
    </div>
    {#if error}<div class="alert alert-danger py-1 px-2 small mt-2 mb-0">{error}</div>{/if}
    <div class="d-flex gap-2 mt-2">
        <button type="button" class="btn btn-sm btn-primary" disabled={saving || !changed} onclick={save}>Save</button>
        <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none" onclick={onClose}>
            Cancel
        </button>
    </div>
</div>

<style>
    .fields {
        max-height: 22rem;
        overflow-x: hidden;
        overflow-y: auto;
    }
    .filter {
        max-width: 16rem;
    }
    .overridden {
        background-color: var(--bs-primary-bg-subtle);
        border-radius: var(--bs-border-radius-sm);
    }
</style>
