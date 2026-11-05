export type EntityType = "release" | "view";
export type NodeRole = "user" | "assistant" | "tool" | "action" | "summary";
export type NodeStatus = "streaming" | "done" | "error" | "stopped";
export type ActionState = "pending" | "running" | "done" | "dismissed";

export interface ToolCallInfo {
    id: string;
    name: string;
    arguments: string;
}

export interface JobField {
    name: string;
    value: string | null;
    group: string;
    choices?: string[];
    description?: string;
}

export interface ProposedTest {
    test_id: string;
    test: string;
    name: string;
    group: string;
    build_system_id: string;
    params: Record<string, string>;
    overrides: Record<string, string>;
    seed?: "last_build" | "defaults" | "build";
    build_number?: number | null;
    fields?: JobField[];
}

export interface ActionResult {
    build_system_id?: string;
    test?: string;
    queue_item?: number | null;
    build_number?: number | null;
    issue?: unknown;
    run_id?: string;
    task_id?: string | null;
    status?: "queued" | "processing" | "completed" | "failed";
    response?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    refresh_error?: string | null;
    plan?: string;
    server?: string;
    tool?: string;
    text?: string;
    error: string | null;
}

export interface ZeusRun {
    run_id: string;
    test_id: string;
    url: string;
    test: string;
    status: string;
    version: string | null;
    prompt: string;
}

export interface ChatAction {
    kind: "execute_tests" | "link_issue" | "unlink_issue" | "zeus_investigation" | "show_run" | "zeus_report" |
        "edit_plan" | "mcp_call" | "post_comment";
    state: ActionState;
    proposal: {
        tests?: ProposedTest[];
        run_id?: string;
        test_id?: string;
        issue_url?: string | null;
        issue_id?: string;
        issue_key?: string | null;
        run_url?: string;
        runs?: ZeusRun[];
        question?: string | null;
        test?: string;
        build_number?: number | null;
        status?: string;
        version?: string | null;
        url?: string;
        report?: string;
        posted_at?: string;
        author?: { id: string; username?: string; name?: string; unknown?: boolean } | null;
        plan?: string;
        key?: string;
        summary?: string[];
        server?: string;
        tool?: string;
        arguments?: Record<string, unknown>;
        message?: string;
    };
    rejected: { test: string; reason: string }[];
    confirmed_by: string | null;
    confirmed_at: string | null;
    dismissed_by: string | null;
    results: ActionResult[];
    refreshed_at?: string | null;
    auto?: boolean;
}

export interface ChatNode {
    node: string;
    parent: string | null;
    role: NodeRole;
    content: string;
    reasoning: string | null;
    user_id: string | null;
    tool_calls: ToolCallInfo[];
    tool_call_id: string | null;
    tool_name: string | null;
    action: ChatAction | null;
    model_name: string | null;
    usage: { prompt_tokens: number; completion_tokens: number } | null;
    memory_snapshot: { memory_id: string; revision: string }[];
    status: NodeStatus;
    error: string | null;
    hidden: boolean;
    auto?: boolean;
    created_at: string;
    updated_at: string;
}

export interface ContextStats {
    window: number;
    used: number;
    last_prompt_tokens: number | null;
    estimated_tokens: number;
    messages_since_compaction: number;
    warn_at?: number;
    compact_at?: number;
}

export interface Busy {
    node: string;
    user_id: string;
    since: string;
}

export interface ChatModelInfo {
    connection: string;
    model: string;
    context_window: number;
    tools: boolean;
}

export interface AssistantIdentity {
    connection: string;
    name: string;
    picture_url: string | null;
    updated_by: string | null;
    updated_at: string | null;
}

export interface Conversation {
    entity_id: string;
    entity_type: EntityType;
    entity_name: string;
    scopes: MemoryScope[];
    configured: boolean;
    model: ChatModelInfo | null;
    assistant: AssistantIdentity | null;
    head: string | null;
    busy: Busy | null;
    nodes: ChatNode[];
    context: ContextStats;
}

export interface Started {
    user_node: ChatNode | null;
    assistant_node: ChatNode;
}

export interface Memory {
    id: string;
    entity_id: string;
    entity_type: EntityType;
    entity_name: string;
    kind: "note" | "finding";
    content: string;
    revision: string | null;
    created_by: string;
    created_at: string;
    updated_by: string;
    updated_at: string;
    source_node: string | null;
}

export interface Revision {
    revision: string;
    memory_id: string;
    entity_id: string;
    action: "create" | "update" | "delete" | "revert";
    before: string | null;
    after: string | null;
    kind: string;
    before_kind: string | null;
    user_id: string;
    source: "manual" | "chat";
    source_node: string | null;
    reverts: string | null;
    created_at: string;
}

export interface ChatMeta {
    configured: boolean;
    messages: number;
    last: { user_id: string; at: string } | null;
}

export type ServerEvent =
    | { type: "snapshot"; conversation: Conversation }
    | { type: "node"; node: ChatNode }
    | { type: "delta"; node: string; content: string; reasoning: string }
    | { type: "tool"; node: string; name: string; state: "running" | "done" | "error" }
    | { type: "state"; head: string | null; busy: Busy | null; context: ContextStats }
    | { type: "memory"; memories: Memory[] }
    | { type: "presence"; users: string[] }
    | { type: "heartbeat" }
    | { type: "error"; message: string };

export interface Connection {
    name: string;
    endpoint: string;
    source: "config" | "database";
    token_set: boolean;
    token_readable: boolean;
    updated_by: string | null;
    updated_at: string | null;
}

export interface DefaultModel {
    connection: string;
    model: string;
    context_window: number;
    tools: boolean;
    vision: boolean;
    set_by: string | null;
    set_at: string | null;
}

export interface ProbedModel {
    id: string;
    name: string;
    context_window: number | null;
    tools: boolean | null;
    vision: boolean | null;
}

export interface ToolTestResult {
    tools: boolean;
    detail: string;
    latency_ms: number;
}

export interface MemoryScope {
    id: string;
    type: EntityType;
    name: string;
}
