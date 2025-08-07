<script lang="ts">
    import { getPicture } from "../Common/UserUtils";
    let { item } = $props();
</script>

{#if item.value === undefined}
    <div class="d-flex align-items-center">
        <div
            class="img-profile-small"
            style="background-image: url('/s/no-user-picture.png');"
        ></div>
        <span class="ms-2">Unassigned</span>
    </div>
{:else}
<div class="d-flex align-items-center">
    <div
        class="img-profile"
        style="background-image: url({getPicture(item.picture_id)});"
    ></div>
    <span class="ms-2">{item.username ?? item.label}</span>
</div>
{/if}
