import { describe, it, expect } from "vitest";
import { getPicture, getUser } from "./UserUtils.js";

describe("getPicture", () => {
    it("returns the storage path for a valid picture id", () => {
        expect(getPicture("abc-123")).toBe("/storage/picture/abc-123");
    });

    it("returns the default no-user-picture for falsy id", () => {
        expect(getPicture(null)).toBe("/s/no-user-picture.png");
        expect(getPicture(undefined)).toBe("/s/no-user-picture.png");
        expect(getPicture("")).toBe("/s/no-user-picture.png");
    });
});

describe("getUser", () => {
    const usersCollection = {
        "user-1": {
            username: "alice",
            full_name: "Alice Smith",
            picture_id: "pic-1",
            id: "user-1",
        },
        "user-2": {
            username: "bob",
            full_name: "Bob Jones",
            picture_id: "pic-2",
            id: "user-2",
        },
    };

    it("returns the user from the collection when found", () => {
        const user = getUser("user-1", usersCollection);
        expect(user.username).toBe("alice");
        expect(user.full_name).toBe("Alice Smith");
    });

    it("returns a ghost user when userId is not in the collection", () => {
        const user = getUser("unknown-id", usersCollection);
        expect(user.username).toBe("ghost");
        expect(user.full_name).toBe("Ghost");
        expect(user.picture_id).toBeUndefined();
        expect(user.id).toBe("unknown-id");
    });

    it("ghost user id matches the requested userId", () => {
        const user = getUser("any-id-123", {});
        expect(user.id).toBe("any-id-123");
    });
});
