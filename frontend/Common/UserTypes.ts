export interface User {
    email: string
    full_name: string,
    id: string,
    picture_id: string,
    registration_date: Date,
    roles: string[],
    username: string,
}

export interface Users {
    [key: string]: User
}
