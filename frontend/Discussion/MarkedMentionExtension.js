import {
    applicationCurrentUser
} from "../argus";

export const MarkdownUserMention = {
    name: "userMention",
    level: "inline",
    start(src) {
        return src.match(/\s@/)?.index;
    },

    tokenizer(src, tokens) {
        const rule = /^\s(@[A-Za-z\d](?:[A-Za-z\d]|-(?=[A-Za-z\d])){0,38})/;
        const match = rule.exec(src);
        if (match) {
            const token = {
                type: "userMention",
                raw: match[0],
                text: match[1].trim(),
                tokens: []
            };
            return token;
        }
    },
    renderer(token) {
        let selfMention = token.text.includes(applicationCurrentUser.username) ? "user-mention-self" : "";
        return ` <span class="user-mention ${selfMention}">${token.text}</span>`;
    }
};
