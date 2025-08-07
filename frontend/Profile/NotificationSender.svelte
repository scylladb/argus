<script lang="ts">
    import { getPicture } from "../Common/UserUtils";
    let { user } = $props();
</script>

<div class="d-flex align-items-center px-2">
    <div class="img-profile" style="background-image: url({getPicture(user?.picture_id)})"></div>
    <div class="ms-3">
        <div class="">{user?.full_name ?? "Ghost"}</div>
        <div class="text-muted">{user?.username ?? "ghost"}</div>
    </div>
</div>

<style>
    .img-profile {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background-color: rgb(163, 163, 163);
        background-clip: border-box;
        background-repeat: no-repeat;
        background-position: center;
        background-size: cover;
    }
</style>
