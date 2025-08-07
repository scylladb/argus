<script lang="ts">
    import { applicationCurrentUser } from "../argus";
    import { getPicture } from "../Common/UserUtils";
    let { user = {} } = $props();
</script>

<div class="d-flex align-items-center p-1">
    <div class="img-profile" style="background-image: url('{getPicture(user.picture_id)}');"></div>
    <div class="ms-2 fw-bold" title={user.full_name ?? "Ghost"}>
        {user.username ?? "ghost"}
    </div>
</div>
