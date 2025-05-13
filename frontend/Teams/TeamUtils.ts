import type { User as IUser } from "../Common/UserTypes";

export const TeamRoutes = {
    CREATE_TEAM: "/api/v1/team/create",
    UPDATE_TEAM: "/api/v1/team/{teamId}/edit",
    GET_TEAM: "/api/v1/team/{teamId}/get",
    DELETE_TEAM: "/api/v1/team/{teamId}/delete",
    GET_TEAMS_FOR_LEADER: "/api/v1/team/leader/{leaderId}/teams",
    GET_TEAMS_FOR_USER: "/api/v1/team/user/{userId}/teams",
    GET_JOBS_FOR_USER: "/api/v1/team/user/{userId}/jobs",
    UPDATE_MOTD_FOR_TEAM: "/api/v1/team/{teamId}/motd/edit",
};

export interface Team {
    id: string,
    name: string,
    leader: string,
    members: string[],
    motd: string
}

export interface ShortJob {
    id: string,
    build_id: string,
    start_time: string,
    release_id: string,
    group_id: string,
    test_id: string,
    assignee: string,
    status: string,
    investigation_status: string,
    build_job_url: string,
}

interface RawTeamManagerError {
    exception: string,
    arguments: string[],
}

export class TeamManagerException extends Error {
    name = "TeamManagerException";
}

export class TeamManagerAPIError {
    exception: string;
    arguments: string[];

    constructor(rawError: RawTeamManagerError) {
        this.exception = rawError.exception;
        this.arguments = rawError.arguments;
    }
}

export interface RawTeamListResponse {
    status: string,
    response: Team[] & RawTeamManagerError
}

export interface RawTeamCreateResponse {
    status: string,
    response: Team & RawTeamManagerError
}

export interface RawTeamUpdateResponse {
    status: string,
    response: { team_id: string, status: string, team: Team } & RawTeamManagerError
}

export interface RawTeamMotdUpdateResponse {
    status: string,
    response: { team_id: string, status: string } & RawTeamManagerError
}
export interface RawTeamGetResponse {
    status: string,
    response: Team & RawTeamManagerError
}

export interface RawTeamDeleteResponse {
    status: string,
    response: { team_id: string, status: string } & RawTeamManagerError
}

export interface RawUserJobsResponse {
    status: string,
    response: ShortJob[] & RawTeamManagerError
}

export interface Member {
    username: string,
    full_name: string,
    picture_id: string,
    id: string
}

export interface UserSelectItem {
    value: string,
    label: string,
    picture_id: string,
    full_name: string,
    user_id: string,
}

export const createUserSelectList = function(users: IUser[], currentUser: IUser): UserSelectItem[] {
    return users
        .map((user) => {
            return {
                value: user.username,
                label: user.username,
                picture_id: user.picture_id,
                full_name: user.full_name,
                user_id: user.id,
            };
        })
        .filter((user) => {
            return user.user_id != currentUser.id;
        });
};
