export const getPicture = function (id) {
    return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
};
