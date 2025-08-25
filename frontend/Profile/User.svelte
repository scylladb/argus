<script lang="ts">
    interface Props {
        item?: any;
    }

    let {
        item = undefined,
    }: Props = $props();
    const getPicture = function (id: string) {
        return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
    };
</script>

<div
    class="d-flex align-items-center"
>
    <div class="">
        <div
            class="img-profile"
            style="background-image: url({getPicture(item.picture_id)});"
            title={item.label || item.username}
        ></div>
    </div>
    <div class="ms-2">
        {item.full_name || item.label}
        <div class="text-muted" style="font-size: small; margin: 0">@{item.label || item.username}</div>
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
