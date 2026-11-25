export interface ExampleGroup {
    title: string;
    examples: string[];
}

export const DOCS_URL = "https://github.com/scylladb/argus/blob/master/docs/release_chat.md";

export const EXAMPLE_GROUPS: ExampleGroup[] = [
    {
        title: "Ask",
        examples: [
            "What failed on the latest release candidate? Give the counts and the test names.",
            "How did rc3 do compared with rc4?",
            "Why did the last run of <test> fail?",
            "Who is assigned to the upgrade tests?",
        ],
    },
    {
        title: "Run tests",
        examples: [
            "Rerun the tests that failed on <version>, on gce.",
            "Run <test> with scylla_version <version>.",
            "Rerun the <group> group with the job's defaults.",
        ],
    },
    {
        title: "Plans and labels",
        examples: [
            "Which labels does the <plan> plan have?",
            "How are the week1 tests of the <plan> plan doing on <version>?",
            "Run the week1 tests of the <plan> plan on gce.",
            "Rerun the week1 tests that failed or did not run on <version>.",
        ],
    },
    {
        title: "Memories and Zeus",
        examples: [
            "Remember that we run tests on GCE when the job supports it.",
            "Add a finding: <what you found>.",
            "Ask Zeus why <test> failed on <version>.",
        ],
    },
];
