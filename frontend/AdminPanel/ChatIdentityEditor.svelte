<script lang="ts">
    import { fetchJson } from "../Common/ApiUtils";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import AssistantAvatar from "../Chat/AssistantAvatar.svelte";
    import type { AssistantIdentity } from "../Chat/types";
    import AvatarCropper from "./AvatarCropper.svelte";

    interface Props {
        connection: string;
        identity: AssistantIdentity | null;
        onSaved: (identity: AssistantIdentity | null) => void;
        onClose: () => void;
    }

    let { connection, identity, onSaved, onClose }: Props = $props();

    const NAME_LIMIT = 40;
    const base = $derived(`/admin/api/v1/chat/connection/${encodeURIComponent(connection)}/identity`);

    let name = $state("");
    let file = $state<File | null>(null);
    let removePicture = $state(false);
    let cropper = $state<AvatarCropper>();
    let working = $state(false);
    let error = $state("");

    $effect.pre(() => {
        name = identity?.name ?? "";
    });

    const choose = (event: Event) => {
        const chosen = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
        error = chosen && !chosen.type.startsWith("image/") ? "Choose an image file" : "";
        file = error ? null : chosen;
        if (file) removePicture = false;
    };

    const save = async () => {
        working = true;
        error = "";
        try {
            const form = new FormData();
            form.append("assistant_name", name.trim());
            if (file && cropper) {
                form.append("picture", await cropper.toBlob(), "avatar.png");
            } else if (removePicture) {
                form.append("remove_picture", "true");
            }
            onSaved(await fetchJson<AssistantIdentity>(base, { method: "POST", body: form }));
        } catch (failure) {
            error = failure instanceof Error ? failure.message : String(failure);
        } finally {
            working = false;
        }
    };

    const remove = async () => {
        working = true;
        try {
            await fetchJson(base, { method: "DELETE" });
            onSaved(null);
        } catch (failure) {
            error = failure instanceof Error ? failure.message : String(failure);
        } finally {
            working = false;
        }
    };
</script>

<ModalWindow on:modalClose={onClose}>
    {#snippet title()}Assistant identity on {connection}{/snippet}
    {#snippet body()}
        <form class="d-flex flex-column gap-3" onsubmit={(event) => { event.preventDefault(); save(); }}>
            <div>
                <label class="form-label" for="identity-name">Name</label>
                <input id="identity-name" class="form-control" bind:value={name} maxlength={NAME_LIMIT} required
                       placeholder="Assistant" />
            </div>
            <div>
                <label class="form-label" for="identity-picture">Picture</label>
                {#if file}
                    <AvatarCropper bind:this={cropper} {file} />
                {:else if identity?.picture_url && !removePicture}
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <AssistantAvatar assistant={identity} size={64} />
                        <button type="button" class="btn btn-sm btn-link text-danger text-decoration-none"
                                onclick={() => (removePicture = true)}>Remove picture</button>
                    </div>
                {/if}
                <input id="identity-picture" class="form-control form-control-sm mt-2" type="file" accept="image/*"
                       onchange={choose} />
            </div>
            {#if error}<div class="alert alert-danger py-1 px-2 small mb-0">{error}</div>{/if}
            <div class="d-flex gap-2">
                {#if identity}
                    <button type="button" class="btn btn-link text-danger text-decoration-none px-0" disabled={working}
                            onclick={remove}>Delete identity</button>
                {/if}
                <button type="button" class="btn btn-link text-body-secondary text-decoration-none ms-auto"
                        onclick={onClose}>Cancel</button>
                <button type="submit" class="btn btn-primary" disabled={working || !name.trim()}>Save</button>
            </div>
        </form>
    {/snippet}
</ModalWindow>
