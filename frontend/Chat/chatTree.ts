import type { ChatNode } from "./types";

export interface Turn {
    opener: ChatNode;
    answers: ChatNode[];
    tools: ChatNode[];
    actions: ChatNode[];
    firstAnswer: ChatNode | null;
}

const byTime = (a: ChatNode, b: ChatNode) => a.created_at.localeCompare(b.created_at);

export const activePath = (nodes: ChatNode[], head: string | null): ChatNode[] => {
    const byId = new Map(nodes.map((node) => [node.node, node]));
    const path: ChatNode[] = [];
    let current = head ? byId.get(head) : undefined;
    while (current) {
        path.push(current);
        current = current.parent ? byId.get(current.parent) : undefined;
    }
    return path.reverse();
};

export const alternativesOf = (nodes: ChatNode[], answer: ChatNode): { siblings: ChatNode[]; index: number } => {
    const siblings = nodes
        .filter((node) => node.parent === answer.parent && node.role === answer.role && !node.hidden)
        .sort(byTime);
    return { siblings, index: siblings.findIndex((node) => node.node === answer.node) };
};

export const splitTurns = (path: ChatNode[]): Turn[] => {
    const turns: Turn[] = [];
    for (const node of path) {
        if (node.role === "user" || node.role === "summary" || turns.length === 0) {
            turns.push({ opener: node, answers: [], tools: [], actions: [], firstAnswer: null });
            if (node.role === "user" || node.role === "summary") continue;
        }
        const turn = turns[turns.length - 1];
        if (node.role === "assistant") {
            turn.answers.push(node);
            turn.firstAnswer ??= node;
        } else if (node.role === "tool") {
            turn.tools.push(node);
        } else if (node.role === "action") {
            turn.actions.push(node);
        }
    }
    return turns;
};

export interface Branch {
    leaf: ChatNode;
    questions: number;
    lastQuestion: ChatNode | null;
    divergence: { kind: "question" | "answer"; node: ChatNode; question: ChatNode | null } | null;
    current: boolean;
}

/** Every branch of the conversation, newest first: one per visible leaf, with where it parts from the active
 * path. */
export const branches = (nodes: ChatNode[], head: string | null): Branch[] => {
    const visible = nodes.filter((node) => !node.hidden);
    const byId = new Map(visible.map((node) => [node.node, node]));
    const parents = new Set(visible.map((node) => node.parent).filter(Boolean));
    const onActive = new Set(activePath(visible, head).map((node) => node.node));
    return visible
        .filter((node) => !parents.has(node.node))
        .map((leaf) => {
            const path = activePath(visible, leaf.node);
            const questions = path.filter((node) => node.role === "user");
            const parted = path.find((node) => !onActive.has(node.node)) ?? null;
            const question = parted?.parent ? byId.get(parted.parent) ?? null : null;
            return {
                leaf,
                questions: questions.length,
                lastQuestion: questions.at(-1) ?? null,
                divergence: parted
                    ? { kind: parted.role === "user" ? "question" : "answer", node: parted,
                        question: parted.role === "user" ? null : question }
                    : null,
                current: leaf.node === head,
            } as Branch;
        })
        .sort((a, b) => b.leaf.created_at.localeCompare(a.leaf.created_at));
};

/** Whether the head has visible children: the next question then starts a new branch. */
export const atForkPoint = (nodes: ChatNode[], head: string | null): boolean =>
    Boolean(head) && nodes.some((node) => node.parent === head && !node.hidden);
