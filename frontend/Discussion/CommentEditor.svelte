<script>
    import { createEventDispatcher, onMount } from "svelte";
    import { parse as markdownParse } from "marked";
    import Fa from "svelte-fa";
    import {
        faHeading,
        faBold,
        faItalic,
        faUnderline,
        faQuoteLeft,
        faListUl,
        faListOl,
        faCode,
        faLink,
        faTasks,
        faAt,
        faLightbulb,
    } from "@fortawesome/free-solid-svg-icons";
    import sha1 from "js-sha1";
    import MentionSelector from "./MentionSelector.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { markdownRendererOptions } from "../markdownOptions";
    export let mode = "post";
    export let runId = "";
    export let commentBody = {
        id: "",
        message: "",
        release: "",
        reactions: {},
        mentions: [],
        user_id: "",
        release_id: "",
        test_run_id: "",
        posted_at: new Date(),
    };
    export let entryType = "comment";

    onMount(() => {
        textArea?.focus();
    });

    const randomTip = function () {
        const editorTips = [
            "You can press Ctrl+Enter instead of clicking Submit",
            "Pressing Esc after starting a mention cancels the mention",
            "Press tab to insert 4 spaces",
        ];
        let randIdx = Math.floor(Math.random() * editorTips.length);
        return editorTips[randIdx];
    };

    const surroundAction = function (sub, lhs, rhs, markup, areaData) {
        return `${lhs}${markup}${sub}${markup}${rhs}`;
    };

    const startAction = function (sub, lhs, rhs, markup, areaData) {
        let lines = areaData.originalText.split("\n");
        let offset = areaData.cursorStart;
        let lineOffset = 0;
        let affectedLine;
        let affectedLineIdx;
        for (const [idx, line] of Object.entries(lines)) {
            affectedLineIdx = parseInt(idx);
            lineOffset += line.length + 1;
            if (lineOffset >= offset) {
                affectedLine = line;
                break;
            }
        }

        if (!affectedLine) {
            console.log("Editor Error: unable to locate affected line");
            return areaData.originalText;
        }

        affectedLine = `${markup}${affectedLine}\n`;
        lines[affectedLineIdx] = affectedLine;

        return lines.join("\n");
    };

    const putAction = function (sub, lhs, rhs, markup, areaData) {
        return `${lhs}${markup}${sub}${rhs}`;
    };

    const buttonActions = {
        heading: [startAction, "### "],
        bold: [surroundAction, "**"],
        italic: [surroundAction, "*"],
        underline: [surroundAction, "__"],
        listOl: [startAction, "1. "],
        listUl: [startAction, "- "],
        code: [surroundAction, "\n```\n"],
        link: [putAction, "[text](url)"],
        tasks: [startAction, "[] "],
        quote: [startAction, "> "],
        mention: [putAction, "@"],
        tab: [putAction, "    "],
        at: [putAction, "@"],
    };
    const dispatch = createEventDispatcher();
    let textArea;
    let mentioning = false;
    let mentionKeyPressed = false;

    const performButtonAction = function (buttonName, markupOverride) {
        let cursorStart = textArea.selectionStart;
        let cursorEnd = textArea.selectionEnd;
        let text = textArea.value;
        let substringLeft = text.substring(0, cursorStart);
        let substringRight = text.substring(cursorEnd);
        let substring = text.substring(cursorStart, cursorEnd);
        let [func, markup] = buttonActions[buttonName];

        let newText = func(
            substring,
            substringLeft,
            substringRight,
            markupOverride || markup,
            {
                cursorStart: cursorStart,
                cursorEnd: cursorEnd,
                originalText: text,
            }
        );
        commentBody.message = newText;
        commentBody = commentBody;
    };

    let elementKey = sha1(`${runId}${commentBody.id}`).slice(0, 8);
    let users = {};
    $: users = $userList;

    const handleMention = function (e) {
        let user = e.detail;
        mentioning = false;
        performButtonAction("mention", `@${user.username}`);
        textArea.focus();
        mentionKeyPressed = false;
    };

    const editorHandleKeyDown = function (e) {
        if (!e.code) return;
        switch (e.code) {
        case "Tab": {
            performButtonAction("tab");
            e.preventDefault();
            break;
        }
        case "Enter": {
            if (!e.ctrlKey) break;
            e.preventDefault();
            handleSubmitComment();
            break;
        }
        }
    };

    const editorBeforeInput = function (e) {
        switch (e.data) {
        case "@": {
            mentioning = true;
            mentionKeyPressed = true;
            e.preventDefault();
            break;
        }
        }
    };

    const handleSubmitComment = function () {
        dispatch("submitComment", commentBody);
    };
</script>

<div class="mb-2 p-2 bg-editor rounded shadow-sm position-relative">
    <ul
        class="nav nav-tabs shadow-sm bg-main"
        id="commentEditorTabs-{elementKey}"
        role="tablist"
    >
        <li class="nav-item" role="presentation">
            <button
                class="nav-link active nav-tab-editor"
                id="editorTabEditor-{elementKey}"
                data-bs-toggle="tab"
                data-bs-target="#editorArea-{elementKey}"
                type="button"
                role="tab">Write</button
            >
        </li>
        <li class="nav-item" role="presentation">
            <button
                class="nav-link nav-tab-editor"
                id="profile-tab"
                data-bs-toggle="tab"
                data-bs-target="#editorPreview-{elementKey}"
                type="button"
                role="tab">Preview</button
            >
        </li>
    </ul>
    <div
        class="tab-content bg-white rounded-bottom border-start border-end border-bottom shadow-sm mb-2"
        id="commentEditorTabContent-{elementKey}"
    >
        <div
            class="tab-pane fade show active"
            id="editorArea-{elementKey}"
            role="tabpanel"
        >
            <div class="bg-main">
                <div
                    class="editor-buttons d-flex align-items-center justify-content-start p-2"
                >
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("heading")}
                    >
                        <Fa icon={faHeading} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("bold")}
                    >
                        <Fa icon={faBold} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("italic")}
                    >
                        <Fa icon={faItalic} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("underline")}
                    >
                        <Fa icon={faUnderline} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("quote")}
                    >
                        <Fa icon={faQuoteLeft} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("code")}
                    >
                        <Fa icon={faCode} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("link")}
                    >
                        <Fa icon={faLink} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("listOl")}
                    >
                        <Fa icon={faListOl} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("listUl")}
                    >
                        <Fa icon={faListUl} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => performButtonAction("tasks")}
                    >
                        <Fa icon={faTasks} />
                    </button>
                    <button
                        class="btn btn-sm btn-outline-dark ms-1"
                        on:click={() => (mentioning = true)}
                    >
                        <Fa icon={faAt} />
                        {#if mentioning}
                            <div class="position-absolute">
                                <MentionSelector
                                    {users}
                                    on:mentionUser={handleMention}
                                    on:closeMention={(e) => {
                                        mentioning = false;
                                        textArea.focus();
                                        if (mentionKeyPressed) {
                                            performButtonAction("at");
                                            mentionKeyPressed = false;
                                            textArea.setSelectionRange(
                                                textArea.selectionStart + 1,
                                                textArea.selectionEnd + 1
                                            );
                                        }
                                    }}
                                />
                            </div>
                        {/if}
                    </button>
                </div>
                <div class="editor-content p-1">
                    <textarea
                        bind:this={textArea}
                        class="w-100 form-control"
                        rows="6"
                        bind:value={commentBody.message}
                        on:keydown={editorHandleKeyDown}
                        on:beforeinput={editorBeforeInput}
                    />
                </div>
            </div>
        </div>
        <div
            class="tab-pane fade"
            id="editorPreview-{elementKey}"
            role="tabpanel"
        >
            {#if commentBody.message}
                <div class="p-2 rounded bg-light">
                    <div class="border rounded p-2 bg-white markdown-body">
                        {@html markdownParse(
                            commentBody.message,
                            markdownRendererOptions
                        )}
                    </div>
                </div>
            {:else}
                <div class="p-2 rounded bg-light" style="height: 10em;">
                    Nothing to preview.
                </div>
            {/if}
        </div>
    </div>
    <div class="d-flex">
        <div class="fs-8 text-muted px-2">
            <span class="fw-bold"><Fa icon={faLightbulb} /> Tip</span>: {randomTip()}
        </div>
        <div class="ms-auto text-end">
            {#if mode == "edit" || entryType != "comment"}
                <button
                    class="btn btn-danger"
                    on:click={() => {
                        dispatch("cancelEditing");
                    }}>Cancel editing</button
                >
            {/if}
            <button class="btn btn-success" on:click={handleSubmitComment}
            >{mode == "post" ? "Submit" : "Update"} {entryType}</button
            >
        </div>
    </div>
</div>

<style>
    .nav-tab-editor {
        border-radius: 0px;
    }

    .bg-editor {
        background-color: #f6f6f6;
    }

    .fs-8 {
        font-size: 0.7em;
    }
</style>
