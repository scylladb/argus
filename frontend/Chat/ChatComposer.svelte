<script lang="ts">
    import Fa from "svelte-fa";
    import { faPaperPlane, faRotateLeft, faRotateRight, faStop } from "@fortawesome/free-solid-svg-icons";
    import { autosize } from "./autosize";

    interface Props {
        entityType: "release" | "view";
        disabledReason?: string;
        busy: boolean;
        canRetry: boolean;
        canUndo: boolean;
        onSend: (text: string, auto: boolean) => Promise<boolean>;
        onStop: () => void;
        onRetry: (auto: boolean) => void;
        onUndo: () => void;
    }

    let { entityType, disabledReason = "", busy, canRetry, canUndo, onSend, onStop, onRetry, onUndo }: Props = $props();

    const AUTO_KEY = "argus.chat.auto";

    let text = $state("");
    let sending = $state(false);
    let auto = $state(readAuto());

    function readAuto(): boolean {
        try {
            return sessionStorage.getItem(AUTO_KEY) === "1";
        } catch {
            return false;
        }
    }

    const toggleAuto = (value: boolean) => {
        auto = value;
        try {
            sessionStorage.setItem(AUTO_KEY, value ? "1" : "0");
        } catch {
            return;
        }
    };

    const blocked = $derived(Boolean(disabledReason) || busy || sending);

    const send = async () => {
        if (!text.trim() || blocked) return;
        sending = true;
        try {
            if (await onSend(text.trim(), auto)) text = "";
        } finally {
            sending = false;
        }
    };

    const handleKey = (event: KeyboardEvent) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            send();
        }
    };
</script>

<div class="composer rounded bg-white shadow-sm p-2">
    <textarea
        class="form-control border-0 shadow-none"
        rows="2"
        placeholder={disabledReason || "Type a question..."}
        aria-label="Question"
        bind:value={text}
        use:autosize={text}
        onkeydown={handleKey}
        disabled={Boolean(disabledReason)}
    ></textarea>
    <div class="d-flex align-items-center gap-2 mt-1">
        <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none" disabled={!canUndo || busy} onclick={onUndo}
                title="Remove the last question and its answer">
            <Fa icon={faRotateLeft} /> Undo
        </button>
        <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none" disabled={!canRetry || busy}
                onclick={() => onRetry(auto)} title="Answer the last question again">
            <Fa icon={faRotateRight} /> Try again
        </button>
        <div class="form-check form-switch small mb-0 ms-auto"
             title="Run the proposals of your questions without waiting for a confirmation">
            <input id="chat-auto-mode" class="form-check-input" type="checkbox" role="switch" checked={auto}
                   onchange={(event) => toggleAuto((event.currentTarget as HTMLInputElement).checked)} />
            <label class="form-check-label" class:text-warning-emphasis={auto} for="chat-auto-mode">Auto mode</label>
        </div>
        {#if busy}
            <button type="button" class="btn btn-sm btn-outline-danger" onclick={onStop}>
                <Fa icon={faStop} /> Stop
            </button>
        {/if}
        <button type="button" class="btn btn-sm btn-primary" disabled={blocked || !text.trim()} onclick={send}>
            <Fa icon={faPaperPlane} /> Send
        </button>
    </div>
</div>

<style>
    textarea {
        resize: none;
        min-height: 3rem;
        max-height: 14rem;
        overflow-y: auto;
    }
</style>
