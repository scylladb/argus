import { describe, it, expect } from "vitest";
import { createUserSelectList, TeamManagerAPIError } from "./TeamUtils";
import type { User } from "../Common/UserTypes";

function makeUser(overrides: Partial<User>): User {
    return {
        email: "test@example.com",
        full_name: "Test User",
        id: "user-0",
        picture_id: "pic-0",
        registration_date: new Date(),
        roles: [],
        username: "testuser",
        ...overrides,
    };
}

describe("createUserSelectList", () => {
    it("maps users to select items with correct fields", () => {
        const users = [makeUser({ id: "u1", username: "alice", full_name: "Alice A", picture_id: "p1" })];
        const currentUser = makeUser({ id: "u-current" });

        const result = createUserSelectList(users, currentUser);
        expect(result).toHaveLength(1);
        expect(result[0]).toEqual({
            value: "alice",
            label: "alice",
            picture_id: "p1",
            full_name: "Alice A",
            user_id: "u1",
        });
    });

    it("filters out the current user", () => {
        const currentUser = makeUser({ id: "u-me", username: "me" });
        const users = [makeUser({ id: "u-me", username: "me" }), makeUser({ id: "u-other", username: "other" })];

        const result = createUserSelectList(users, currentUser);
        expect(result).toHaveLength(1);
        expect(result[0].user_id).toBe("u-other");
    });

    it("returns empty array when only the current user is in the list", () => {
        const currentUser = makeUser({ id: "u1" });
        const users = [makeUser({ id: "u1" })];

        expect(createUserSelectList(users, currentUser)).toEqual([]);
    });

    it("returns empty array for empty input", () => {
        const currentUser = makeUser({ id: "u1" });
        expect(createUserSelectList([], currentUser)).toEqual([]);
    });
});

describe("TeamManagerAPIError", () => {
    it("stores exception and arguments from raw error", () => {
        const err = new TeamManagerAPIError({
            exception: "TeamNotFound",
            arguments: ["team-42"],
        });
        expect(err.exception).toBe("TeamNotFound");
        expect(err.arguments).toEqual(["team-42"]);
    });
});
