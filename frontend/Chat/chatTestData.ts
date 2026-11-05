import type { ChatAction, ChatNode } from "./types";

let clock = 0;

export const chatNode = (id: string, role: ChatNode["role"], parent: string | null,
                         extra: Partial<ChatNode> = {}): ChatNode => ({
    node: id, parent, role, content: "", reasoning: null, user_id: "u1", tool_calls: [], tool_call_id: null,
    tool_name: null, action: null, model_name: "gemma", usage: null, memory_snapshot: [], status: "done",
    error: null, hidden: false, created_at: new Date(Date.UTC(2030, 0, 1, 0, 0, clock++)).toISOString(),
    updated_at: "", ...extra,
});

export const startAction = (extra: Partial<ChatAction> = {}): ChatAction => ({
    kind: "execute_tests",
    state: "pending",
    proposal: {
        tests: [{
            test_id: "t1", test: "upgrades/rolling_upgrade", name: "rolling_upgrade", group: "upgrades",
            build_system_id: "scylla-2025.1/upgrades/rolling_upgrade",
            params: { backend: "gce", scylla_version: "2025.1.0" }, overrides: { backend: "gce" },
        }],
    },
    rejected: [{ test: "upgrades/azure_only", reason: "gce is not a choice of backend (azure)" }],
    confirmed_by: null, confirmed_at: null, dismissed_by: null, results: [], ...extra,
});

export const zeusAction = (extra: Partial<ChatAction> = {}): ChatAction => ({
    kind: "zeus_investigation",
    state: "pending",
    proposal: {
        runs: [{ run_id: "r1", test_id: "t1", url: "/test/scylla-2025.1/upgrades/rolling_upgrade/11",
                 test: "upgrades/rolling_upgrade", status: "failed",
                 version: "2025.1.0~rc4", prompt: "Investigate the test run r1" }],
        question: "Why did the upgrade fail?",
    },
    rejected: [],
    confirmed_by: null, confirmed_at: null, dismissed_by: null, results: [], ...extra,
});

export const showRunAction = (): ChatAction => ({
    kind: "show_run",
    state: "done",
    proposal: { run_id: "r1", test_id: "t1", test: "upgrades/rolling_upgrade", build_number: 11, status: "failed",
                version: "2025.1.0~rc4", url: "/test/scylla-2025.1/upgrades/rolling_upgrade/11" },
    rejected: [], confirmed_by: null, confirmed_at: null, dismissed_by: null, results: [],
});

export const zeusReportAction = (): ChatAction => ({
    kind: "zeus_report",
    state: "done",
    proposal: { run_id: "r1", test: "rolling-upgrade/rolling-upgrade-centos9-test", build_number: 11,
                url: "/test/scylla-2025.1/rolling-upgrade/rolling-upgrade-centos9-test/11",
                report: "## Investigation\n\n**Root cause**: out of memory on node-2.",
                posted_at: new Date().toISOString(), author: { id: "z", username: "zeus-bot", name: "Zeus" } },
    rejected: [], confirmed_by: null, confirmed_at: null, dismissed_by: null, results: [],
});
