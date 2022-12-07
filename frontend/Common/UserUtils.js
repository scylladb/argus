export const getPicture = function (id) {
    return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
};

export const getUser = function (userId, usersCollection) {
    const GHOST_USER = {
        username: "ghost",
        full_name: "Ghost",
        picture_id: undefined,
        id: userId,
    };

    return usersCollection[userId] ? usersCollection[userId] : GHOST_USER;
};
