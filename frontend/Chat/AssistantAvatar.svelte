<script lang="ts">
    import Fa from "svelte-fa";
    import { faRobot } from "@fortawesome/free-solid-svg-icons";
    import type { AssistantIdentity } from "./types";

    interface Props {
        assistant: Pick<AssistantIdentity, "name" | "picture_url"> | null;
        size?: number;
    }

    let { assistant, size = 24 }: Props = $props();
</script>

{#if assistant?.picture_url}
    <img class="avatar rounded-circle flex-shrink-0" src={assistant.picture_url} alt="" width={size} height={size} />
{:else}
    <span class="avatar rounded-circle flex-shrink-0 d-inline-flex align-items-center justify-content-center
                 bg-secondary-subtle text-secondary-emphasis" style:width="{size}px" style:height="{size}px"
          aria-hidden="true">
        <Fa icon={faRobot} size="xs" />
    </span>
{/if}

<style>
    .avatar {
        object-fit: cover;
    }
</style>
