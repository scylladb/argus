<script>
    import { faObjectGroup } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    export let item = undefined;
    export let isActive = false;
    export let isFirst = false;
    export let isHover = false;
</script>

<div
    class:view-active={isActive}
    class:view-first={isFirst}
    class:view-hover={isHover}
    class="view-element border-bottom"
>
    <div class="d-flex align-items-center p-2">
        <div>
            <Fa icon={faObjectGroup}/>
        </div>
        <div class="ms-2 text-start">
            <div>{item?.display_name || item.name}</div>
            <div class="text-muted view-label">{item.description}</div>
        </div>
    </div>
</div>

<style>
    .view-first {
        background-color: #ffffff;
    }

    .view-active {
        background-color: #6b9cf7;
    }

    .view-hover {
        background-color: #4c66f8;
        color: white;
        cursor: pointer;
    }

    .view-element:hover .view-label {
        color: #c4c4c4 !important;
    }
</style>
