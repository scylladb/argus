<script lang="ts">
    import Fa from "svelte-fa";
    import { faPen, faPlus, faRotateLeft, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../Common/ApiUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import { postJson } from "../Chat/chatApi";
    import { ago } from "../Chat/chatFormat";
    import { autosize } from "../Chat/autosize";

    const API = "/admin/api/v1/chat";
    const MODES: Record<string, string> = {
        always: "Always",
        on_demand: "On demand",
        off: "Off",
    };

    interface PromptInfo {
        template: string;
        default: string;
        edited: boolean;
        placeholders: string[];
        required: string[];
        updated_at: string | null;
    }

    interface Skill {
        name: string;
        description: string;
        content: string;
        mode: "always" | "on_demand" | "off";
        updated_at: string | null;
    }

    let prompt = $state<PromptInfo | null>(null);
    let draft = $state("");
    let promptError = $state("");
    let skills = $state<Skill[] | null>(null);
    let form = $state<(Skill & { editing: boolean }) | null>(null);
    let skillError = $state("");
    let working = $state(false);

    const fail = (error: unknown) =>
        sendMessage("error", error instanceof Error ? error.message : String(error), "ChatPromptManager");
    const message = (error: unknown) => (error instanceof Error ? error.message : String(error));

    const showPrompt = (info: PromptInfo) => {
        prompt = info;
        draft = info.template;
        promptError = "";
    };

    const load = async () => {
        try {
            showPrompt(await fetchJson<PromptInfo>(`${API}/prompt`));
            skills = await fetchJson<Skill[]>(`${API}/skills`);
        } catch (error) {
            fail(error);
        }
    };

    const savePrompt = async () => {
        working = true;
        try {
            showPrompt(await postJson<PromptInfo>(`${API}/prompt`, { template: draft }, "PUT"));
        } catch (error) {
            promptError = message(error);
        } finally {
            working = false;
        }
    };

    const resetPrompt = async () => {
        working = true;
        try {
            showPrompt(await postJson<PromptInfo>(`${API}/prompt`, undefined, "DELETE"));
        } catch (error) {
            promptError = message(error);
        } finally {
            working = false;
        }
    };

    const saveSkill = async () => {
        if (!form) return;
        working = true;
        try {
            await postJson(`${API}/skill`, { name: form.name.trim(), description: form.description,
                                             content: form.content, mode: form.mode });
            form = null;
            skillError = "";
            skills = await fetchJson<Skill[]>(`${API}/skills`);
        } catch (error) {
            skillError = message(error);
        } finally {
            working = false;
        }
    };

    const deleteSkill = async (skill: Skill) => {
        try {
            await postJson(`${API}/skill/${encodeURIComponent(skill.name)}`, undefined, "DELETE");
            skills = await fetchJson<Skill[]>(`${API}/skills`);
        } catch (error) {
            fail(error);
        }
    };

    load();
</script>

<section class="rounded bg-white shadow-sm p-3">
    <div class="d-flex align-items-center mb-2 gap-2">
        <h3 class="h6 mb-0">System prompt</h3>
        {#if prompt?.edited}
            <span class="badge text-bg-info">Edited{prompt.updated_at ? ` ${ago(prompt.updated_at)}` : ""}</span>
        {:else if prompt}
            <span class="badge text-bg-light">Default</span>
        {/if}
    </div>
    {#if prompt}
        <div class="small text-body-secondary mb-1 d-flex flex-wrap gap-1 align-items-center">
            Placeholders:
            {#each prompt.placeholders as name (name)}
                <code class="rounded bg-light-one px-1" title={prompt.required.includes(name) ? "Required" : "Optional"}
                      >{`{${name}}`}{prompt.required.includes(name) ? "*" : ""}</code>
            {/each}
        </div>
        <textarea class="form-control form-control-sm font-monospace template bg-light-one border-0" rows="12"
                  aria-label="System prompt" bind:value={draft} use:autosize={draft}></textarea>
        {#if promptError}<div class="alert alert-danger py-1 px-2 small mt-2 mb-0">{promptError}</div>{/if}
        <div class="d-flex gap-2 mt-2">
            <button type="button" class="btn btn-sm btn-primary" disabled={working || draft === prompt.template}
                    onclick={savePrompt}>Save</button>
            <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none"
                    disabled={working || !prompt.edited} onclick={resetPrompt}>
                <Fa icon={faRotateLeft} /> Reset to default
            </button>
        </div>
    {:else}
        <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
    {/if}
</section>

<section class="rounded bg-white shadow-sm p-3">
    <div class="d-flex align-items-center mb-2">
        <h3 class="h6 mb-0">Skills</h3>
        <button type="button" class="btn btn-sm btn-outline-primary ms-auto"
                onclick={() => (form = { name: "", description: "", content: "", mode: "always", updated_at: null,
                                         editing: false })}>
            <Fa icon={faPlus} /> Add skill
        </button>
    </div>

    {#if form}
        <form class="rounded bg-light-one p-2 mb-2 d-flex flex-column gap-2 small"
              onsubmit={(event) => { event.preventDefault(); saveSkill(); }}>
            <div class="row g-2">
                <div class="col-md-4">
                    <label class="form-label mb-0" for="skill-name">Name</label>
                    <input id="skill-name" class="form-control form-control-sm" bind:value={form.name}
                           disabled={form.editing} required pattern="[A-Za-z0-9_\-]+" maxlength="64" />
                </div>
                <div class="col-md-3">
                    <label class="form-label mb-0" for="skill-mode">Mode</label>
                    <select id="skill-mode" class="form-select form-select-sm" bind:value={form.mode}>
                        {#each Object.entries(MODES) as [value, label] (value)}
                            <option {value}>{label}</option>
                        {/each}
                    </select>
                </div>
                <div class="col-md-5">
                    <label class="form-label mb-0" for="skill-description">Description</label>
                    <input id="skill-description" class="form-control form-control-sm" bind:value={form.description}
                           maxlength="300" placeholder={form.mode === "on_demand" ? "When to load it" : ""} />
                </div>
            </div>
            <div>
                <label class="form-label mb-0" for="skill-content">Text</label>
                <textarea id="skill-content" class="form-control form-control-sm" rows="5" bind:value={form.content}
                          use:autosize={form.content} required></textarea>
            </div>
            {#if skillError}<div class="alert alert-danger py-1 px-2 mb-0">{skillError}</div>{/if}
            <div class="d-flex gap-2">
                <button type="submit" class="btn btn-sm btn-primary" disabled={working}>Save</button>
                <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none"
                        onclick={() => ((form = null), (skillError = ""))}>Cancel</button>
            </div>
        </form>
    {/if}

    {#if skills === null}
        <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
    {:else if skills.length === 0}
        <div class="text-body-secondary small">No skills yet.</div>
    {:else}
        <div class="d-flex flex-column gap-2">
            {#each skills as skill (skill.name)}
                <div class="rounded bg-light-one p-2 small">
                    <div class="d-flex align-items-center gap-2">
                        <span class="fw-semibold font-monospace">{skill.name}</span>
                        <span class="badge" class:text-bg-success={skill.mode === "always"}
                              class:text-bg-info={skill.mode === "on_demand"}
                              class:text-bg-secondary={skill.mode === "off"}>{MODES[skill.mode]}</span>
                        <span class="text-body-secondary text-truncate">{skill.description}</span>
                        <button type="button" class="btn btn-sm btn-link p-0 ms-auto" aria-label="Edit {skill.name}"
                                onclick={() => (form = { ...skill, editing: true })}><Fa icon={faPen} /></button>
                        <button type="button" class="btn btn-sm btn-link text-danger p-0" aria-label="Delete {skill.name}"
                                onclick={() => deleteSkill(skill)}><Fa icon={faTrash} /></button>
                    </div>
                    <div class="text-body-secondary skill-text mt-1">{skill.content}</div>
                </div>
            {/each}
        </div>
    {/if}
</section>

<style>
    .template {
        min-height: 12rem;
        max-height: 36rem;
    }
    .skill-text {
        white-space: pre-wrap;
        max-height: 6rem;
        overflow: hidden;
    }
</style>
