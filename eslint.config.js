import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import svelte from "eslint-plugin-svelte";
import globals from "globals";

export default [
    js.configs.recommended,
    ...svelte.configs["flat/recommended"],
    {
        files: ["**/*.ts", "**/*.js"],
        languageOptions: {
            parser: tsparser,
            ecmaVersion: "latest",
            sourceType: "module",
            globals: {
                ...globals.browser,
                ...globals.node,
            },
        },
        plugins: {
            "@typescript-eslint": tseslint,
        },
        rules: {
            ...tseslint.configs.recommended.rules,
            "max-len": ["error", { code: 144 }],
            indent: ["error", 4],
            "linebreak-style": ["error", "unix"],
            quotes: ["error", "double"],
            semi: ["error", "always"],
        },
    },
    {
        files: ["**/*.svelte"],
        languageOptions: {
            parser: (await import("svelte-eslint-parser")).default,
            parserOptions: {
                parser: tsparser,
            },
            globals: {
                ...globals.browser,
            },
        },
        plugins: {
            "@typescript-eslint": tseslint,
        },
        rules: {
            ...tseslint.configs.recommended.rules,
            "max-len": ["error", { code: 144 }],
            indent: ["error", 4],
            "linebreak-style": ["error", "unix"],
            quotes: ["error", "double"],
            semi: ["error", "always"],
            "svelte/require-each-key": "off",
        },
    },
];
