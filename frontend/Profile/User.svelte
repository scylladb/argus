<script>
    export let item = undefined;
    export let isActive = false;
    export let isFirst = false;
    export let isHover = false;
    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
    };
</script>

<div
    class:user-active={isActive}
    class:user-first={isFirst}
    class:user-hover={isHover}
    class="user-element"
>
    <div class="d-flex align-items-center">
        <div class="ms-2">
            <div
                class="img-profile"
                style="background-image: url({getPicture(item.picture_id)});"
                title={item.label || item.username}
            />
        </div>
        <div class="ms-2 text-start">
            <div>{item.full_name ?? item.label}</div>
            <div class="text-muted user-label">{item.label || item.username}</div>
        </div>
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

    .user-first {
        background-color: #ffffff;
    }

    .user-active {
        background-color: #6b9cf7;
    }

    .user-hover {
        background-color: #4c66f8;
        color: white;
        cursor: pointer;
    }

    .user-element:hover .user-label {
        color: #c4c4c4 !important;
    }
</style>
