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
