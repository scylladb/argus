import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        include: ["frontend/**/*.test.{js,ts}"],
        environment: "jsdom",
    },
});
