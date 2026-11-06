import type { ChatNode, Conversation, ServerEvent } from "./types";

const upsert = (nodes: ChatNode[], node: ChatNode): ChatNode[] => {
    const index = nodes.findIndex((existing) => existing.node === node.node);
    if (index < 0) return [...nodes, node];
    const copy = nodes.slice();
    copy[index] = node;
    return copy;
};

export const applyEvent = (conversation: Conversation, event: ServerEvent): Conversation => {
    switch (event.type) {
        case "snapshot":
            return event.conversation;
        case "node":
            return { ...conversation, nodes: upsert(conversation.nodes, event.node) };
        case "delta": {
            const node = conversation.nodes.find((existing) => existing.node === event.node);
            if (!node) return conversation;
            return {
                ...conversation,
                nodes: upsert(conversation.nodes, {
                    ...node,
                    content: node.content + event.content,
                    reasoning: event.reasoning ? (node.reasoning ?? "") + event.reasoning : node.reasoning,
                }),
            };
        }
        case "state":
            return { ...conversation, head: event.head, busy: event.busy, context: event.context };
        default:
            return conversation;
    }
};
