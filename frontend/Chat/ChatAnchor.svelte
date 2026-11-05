<script lang="ts">
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faComments } from "@fortawesome/free-solid-svg-icons";
    import { applicationCurrentUser } from "../argus.js";
    import { fetchJson } from "../Common/ApiUtils";
    import type { User } from "../Common/UserTypes";
    import { userList } from "../Stores/UserlistSubscriber.js";
    import ChatModal from "./ChatModal.svelte";
    import { chatBase } from "./chatApi";
    import { ago, displayName } from "./chatFormat";
    import type { ChatMeta, EntityType } from "./types";

    interface Props {
        dashboardObject: { id: string; name?: string; display_name?: string };
        dashboardObjectType?: EntityType;
    }

    let { dashboardObject, dashboardObjectType = "view" }: Props = $props();

    let meta = $state<ChatMeta | null>(null);
    let error = $state("");
    let open = $state(false);

    const users = $derived($userList as Record<string, User>);
    const isAdmin = ((applicationCurrentUser as { roles?: string[] }).roles ?? []).includes("ROLE_ADMIN");
    const entityName = $derived(dashboardObject.display_name || dashboardObject.name || "");

    const loadMeta = async () => {
        try {
            meta = await fetchJson<ChatMeta>(`${chatBase(dashboardObjectType, dashboardObject.id)}/meta`);
            error = "";
        } catch (e) {
            error = e instanceof Error ? e.message : String(e);
        }
    };

    onMount(loadMeta);
</script>

<div class="chat-anchor rounded bg-light-one shadow-sm px-3 py-2 d-flex align-items-center gap-2 flex-wrap mb-2">
    <Fa icon={faComments} />
    <span class="fw-semibold">Chat</span>
    <span class="small text-body-secondary">
        {#if error}
            Could not load the chat: {error}
        {:else if !meta}
            Loading…
        {:else if !meta.configured}
            No chat model is configured yet
        {:else if meta.last}
            {meta.messages} question{meta.messages === 1 ? "" : "s"} · last by {displayName(meta.last.user_id, users)}
            {ago(meta.last.at)}
        {:else}
            No questions yet.
        {/if}
    </span>
    <button type="button" class="btn btn-sm btn-primary ms-auto" onclick={() => (open = true)}>Open chat</button>
</div>

{#if open}
    <ChatModal
        entityType={dashboardObjectType}
        entityId={dashboardObject.id}
        {entityName}
        {isAdmin}
        onClose={() => {
            open = false;
            loadMeta();
        }}
    />
{/if}
