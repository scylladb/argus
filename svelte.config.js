import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const typescript = vitePreprocess({ script: true });

export default {
    preprocess: {
        ...typescript,
        script: (options) => (options.filename?.includes("/node_modules/") ? undefined : typescript.script?.(options)),
    },
};
