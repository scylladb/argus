<script lang="ts">
    import Fa from "svelte-fa";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";

    let { entries, label, btnClass = "btn-outline-success" } = $props();

    const copy = (command: string) => {
        navigator.clipboard.writeText(command);
        sendMessage("success", `\`${command}\` has been copied to your clipboard`);
    };
</script>

{#if entries.length > 0}
    <div class="btn-group">
        <button
            type="button"
            class="btn {btnClass} dropdown-toggle"
            data-bs-toggle="dropdown"
            data-bs-auto-close="outside"
            data-bs-popper-config={'{"strategy":"fixed"}'}
            aria-expanded="false"
        >
            <Fa icon={faCopy} /> {label}
        </button>
        <div class="dropdown-menu p-2">
            {#each entries as entry (entry.label)}
                <div class="mb-2">
                    <div class="small fw-bold">{entry.label}</div>
                    {#each entry.commands as command (command)}
                        <div class="input-group input-group-sm mb-1">
                            <input
                                type="text"
                                class="form-control font-monospace"
                                readonly
                                value={command}
                                size={command.length}
                                aria-label="{entry.label} command"
                            />
                            {#if navigator.clipboard}
                                <button
                                    type="button"
                                    class="btn btn-outline-success"
                                    title="Copy"
                                    aria-label="Copy {command}"
                                    onclick={() => copy(command)}
                                >
                                    <Fa icon={faCopy} />
                                </button>
                            {/if}
                        </div>
                    {/each}
                </div>
            {/each}
        </div>
    </div>
{/if}

<style>
    .dropdown-menu {
        min-width: max-content;
    }
</style>
