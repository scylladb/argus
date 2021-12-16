<script>
    export let item = undefined;
    export let isActive = false;
    export let isFirst = false;
    export let isHover = false;

    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/static/no-user-picture.png";
    };
</script>

<div
    class:user-active={isActive}
    class:user-first={isFirst}
    class:user-hover={isHover}
>
    <div class="p-1">
        <div class="d-inline-block">
            <img
                class="img-profile"
                src={getPicture(item.picture_id)}
                alt={item.username}
            />
        </div>
        <div class="d-inline-block">
            {item.full_name}
        </div>
        <div hidden>{item.label}</div>
    </div>
</div>

<style>
    .img-profile {
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
    }

    .user-first {
        background-color: #a0a0a0;
    }

    .user-active {
        background-color: #2058c0;
    }

    .user-hover {
        background-color: #414141;
        color: white;
        cursor: pointer;
    }

</style>
