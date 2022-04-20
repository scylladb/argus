import highlight from "highlight.js";
export let markdownRendererOptions = {
    highlight: function (code, lang) {
        const hljs = highlight;
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, {
            language
        }).value;
    },
    gfm: true,
    langPrefix: 'hljs language-',
    breaks: true,
};
