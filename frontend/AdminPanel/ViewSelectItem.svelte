<script lang="ts">
    interface Props {
        item?: any;
        isActive?: boolean;
        isFirst?: boolean;
        isHover?: boolean;
    }

    let {
        item = undefined,
        isActive = false,
        isFirst = false,
        isHover = false
    }: Props = $props();

    const ITEM_TYPES = {
        test: "T",
        group: "G",
        release: "R",
        special: "S",
        run: "R",
    };
</script>


<div
    class="p-2 border-bottom border-top"
    class:rounded-top={isFirst}
    class:bg-primary={isHover}
    class:hover={isHover}
>
    <div class="d-flex">
        <div class="me-2"><span class="fw-bold">{ITEM_TYPES[item.type]}</span></div>
        <div>{item.pretty_name || item.name}</div>
        <div class="ms-auto d-flex justify-content-end align-items-center text-sm">
            {#if item.test}
                <div>
                    <span class="fw-bold">{item.test?.name}</span>
                </div>
            {/if}
            {#if item.release}
                <div class="ms-2">
                    <span class="fw-bold">{item.release?.name}</span>
                </div>
            {/if}
            {#if item.group}
                <div class="ms-2">
                    {item.group?.pretty_name || item.group?.name}
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    .hover {
        cursor: pointer;
    }

    .text-sm {
        font-size: 0.8em;
    }
</style>
