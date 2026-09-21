<script lang="ts">
    interface Props {
        metadata?: Record<string, string>;
        compact?: boolean;
    }

    let { metadata = {}, compact = false }: Props = $props();

    const DESCRIPTION_KEY = "description";
    const KEY_ORDER = ["tier", "test_type", "duration_class", "supported_backends"];
    const LIST_KEYS = ["supported_backends"];
    const BADGE_CLASSES: Record<string, string> = {
        tier: "text-bg-primary",
        test_type: "text-bg-info",
        duration_class: "text-bg-secondary",
        supported_backends: "text-bg-dark",
    };

    const parseList = function (value: string): string[] {
        try {
            const parsed = JSON.parse(value);
            return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [value];
        } catch {
            return [value];
        }
    };

    const description = $derived(metadata?.[DESCRIPTION_KEY] ?? "");

    const labels = $derived.by(() => {
        const keys = Object.keys(metadata ?? {}).filter((key) => key !== DESCRIPTION_KEY);
        const ordered = [
            ...KEY_ORDER.filter((key) => keys.includes(key)),
            ...keys.filter((key) => !KEY_ORDER.includes(key)),
        ];

        return ordered
            .map((key) => ({
                key,
                badgeClass: BADGE_CLASSES[key] ?? "text-bg-light",
                values: (LIST_KEYS.includes(key) ? parseList(metadata[key]) : [metadata[key]])
                    .filter((value) => value !== "" && value.toLowerCase() !== "n/a")
                    .map((value) => (KEY_ORDER.includes(key) ? value : `${key}: ${value}`)),
            }))
            .filter((label) => label.values.length > 0);
    });
</script>

{#if labels.length > 0 || (description && !compact)}
    <div class="test-metadata">
        {#if description && !compact}
            <div class="text-muted metadata-description">{description}</div>
        {/if}
        {#if labels.length > 0}
            <div class="d-flex flex-wrap gap-1 mt-1">
                {#each labels as label (label.key)}
                    {#each label.values as value}
                        <span class="badge {label.badgeClass}" title={label.key}>{value}</span>
                    {/each}
                {/each}
            </div>
        {/if}
    </div>
{/if}

<style>
    .metadata-description {
        font-size: 0.85em;
    }
</style>
