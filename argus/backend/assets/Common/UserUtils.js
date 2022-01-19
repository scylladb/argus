export const getPicture = function (id) {
    return id ? `/storage/picture/${id}` : "/static/no-user-picture.png";
};
