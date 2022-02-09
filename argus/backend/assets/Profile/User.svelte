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
    <div class="d-flex align-items-center">
        <div class="ms-2">
            <img
                class="img-profile"
                src={getPicture(item.picture_id)}
                alt={item.label}
            />
        </div>
        <div class="ms-2">
            {item.full_name}
            <div class="text-muted">{item.label}</div>
        </div>
    </div>
</div>

<style>
    .img-profile {
        width: 32px;
        border-radius: 50%;
        object-fit: cover;
    }

    .user-first {
        background-color: #ffffff;
    }

    .user-active {
        background-color: #6b9cf7;
    }

    .user-hover {
        background-color: #537cee;
        color: white;
        cursor: pointer;
    }

</style>
