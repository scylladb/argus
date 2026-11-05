import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/svelte";

vi.mock("./CloneTargetSelector.svelte", async () => await import("./testing/ExitOnMount.svelte"));
vi.mock("./CloneSuccess.svelte", async () => await import("./testing/ExitOnMount.svelte"));
vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import JenkinsBuildModal from "./JenkinsBuildModal.svelte";
import JenkinsCloneModal from "./JenkinsCloneModal.svelte";

const BUILD_ID = "scylla-master/rolling-upgrade/rolling-upgrade-debian13-test";
const RUN_BUILD_NUMBER = 412;

const ok = (response: unknown) => ({ json: async () => ({ status: "ok", response }) });

function stubFetch() {
    const fetchMock = vi.fn(async (url: string) => {
        if (url.startsWith("/api/v1/jenkins/clone/targets")) return ok({ targets: [] });
        if (url === "/api/v1/jenkins/clone/create") return ok({ newBuildId: "fork/cloned-test" });
        return { json: async () => ({ status: "error", response: { arguments: ["stop"] } }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

async function paramsRequest(fetchMock: ReturnType<typeof stubFetch>) {
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/jenkins/params")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => url === "/api/v1/jenkins/params")!;
    return JSON.parse((init as RequestInit).body as string);
}

describe("parameter fetch of the run dialogs", () => {
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

    it("rebuild asks for the parameters of the run's build", async () => {
        const fetchMock = stubFetch();
        render(JenkinsBuildModal, {
            props: { buildId: BUILD_ID, buildNumber: RUN_BUILD_NUMBER, pluginName: "scylla-cluster-tests" },
        });

        expect(await paramsRequest(fetchMock)).toEqual({ buildId: BUILD_ID, buildNumber: RUN_BUILD_NUMBER });
    });

    it("clone asks for the parameters of the run's build of the source job", async () => {
        const fetchMock = stubFetch();
        render(JenkinsCloneModal, {
            props: {
                buildId: BUILD_ID,
                buildNumber: RUN_BUILD_NUMBER,
                pluginName: "scylla-cluster-tests",
                testId: "a1b2c3d4-0000-4000-8000-000000000001",
                oldTestName: "rolling-upgrade-debian13-test",
                releaseId: "c3d4e5f6-0000-4000-8000-000000000003",
                groupId: "d4e5f6a7-0000-4000-8000-000000000004",
            },
        });

        expect(await paramsRequest(fetchMock)).toEqual({ buildId: BUILD_ID, buildNumber: RUN_BUILD_NUMBER });
    });
});
