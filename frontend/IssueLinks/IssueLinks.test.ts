import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";

vi.mock("../WorkArea/TestRuns.svelte", () => ({ default: vi.fn() }));
vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Stores/UserlistSubscriber.js", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({});
            return () => {};
        },
    },
}));

import IssueLinks from "./IssueLinks.svelte";

const ISSUE = {
    subtype: "jira",
    id: "j-1",
    state: "in progress",
    added_on: "2026-09-14T08:21:05Z",
    labels: [],
    user_id: "u-2",
    key: "SCT-1234",
    summary: "Nemesis fails to restart node",
    project: "SCT",
    permalink: "https://zxqtesting.atlassian.net/browse/SCT-1234",
    assignees: [],
};

const link = (run: number, testName: string) => ({
    run_id: `a7b1c2d3-0000-4000-8000-${String(run).padStart(12, "0")}`,
    test_id: "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11",
    test_name: testName,
    plugin_name: "scylla-cluster-tests",
    status: "failed",
    start_time: "2026-09-30T22:10:44Z",
    build_id: `frobnicator/${testName}`,
    build_number: run,
    scylla_version: "2026.2.0~dev",
    product_version: null,
    linked_on: null,
    url: `http://testserver/test/frobnicator/${testName}/${run}`,
});

const stubFetch = (body: unknown) => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, json: () => Promise.resolve(body) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("IssueLinks", () => {
    it("requests the lookup for the key", async () => {
        const fetchMock = stubFetch({ status: "ok", response: { issue: null, links: [] } });

        render(IssueLinks, { props: { issueKey: "SCT-1234" } });

        await screen.findByText("Argus holds no issue SCT-1234.");
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/issues/SCT-1234/links", undefined);
    });

    it("renders the issue and its runs in order", async () => {
        stubFetch({
            status: "ok",
            response: { issue: ISSUE, links: [link(413, "longevity-frobnicator-4h"), link(97, "artifacts-quux")] },
        });

        render(IssueLinks, { props: { issueKey: "SCT-1234" } });

        expect(await screen.findByText("Nemesis fails to restart node")).toBeTruthy();
        expect(screen.getByText("2 linked runs")).toBeTruthy();
        expect(screen.getByText("1 test · 1 version · 2 failed")).toBeTruthy();
        const names = screen.getAllByText(/^(longevity-frobnicator-4h|artifacts-quux)$/).map((el) => el.textContent);
        expect(names).toEqual(["longevity-frobnicator-4h", "artifacts-quux"]);
    });

    it("shows that Argus holds no such issue", async () => {
        stubFetch({ status: "ok", response: { issue: null, links: [] } });

        render(IssueLinks, { props: { issueKey: "sct-1234" } });

        expect(await screen.findByText("Argus holds no issue SCT-1234.")).toBeTruthy();
    });

    it("shows an issue without runs", async () => {
        stubFetch({ status: "ok", response: { issue: ISSUE, links: [] } });

        render(IssueLinks, { props: { issueKey: "SCT-1234" } });

        expect(await screen.findByText("Nemesis fails to restart node")).toBeTruthy();
        expect(screen.getByText("No test runs are linked to SCT-1234.")).toBeTruthy();
    });

    it("shows the API error", async () => {
        const message = "Not an issue key: 'SCT1234'. Expected a Jira key such as SCT-1234.";
        stubFetch({ status: "error", response: { exception: "IssueServiceException", arguments: [message] } });

        render(IssueLinks, { props: { issueKey: "SCT1234" } });

        expect(await screen.findByText(message)).toBeTruthy();
    });
});
