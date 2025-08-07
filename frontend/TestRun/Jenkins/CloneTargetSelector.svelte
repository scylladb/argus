<script>
    import queryString from "query-string";
    import Select from "svelte-select";
    import { sendMessage } from "../../Stores/AlertStore";
    import { createEventDispatcher, onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import { JENKINS_ADVANCED_SETTINGS } from "../../Common/JenkinsSettingsHelp";

    /**
     * @typedef {Object} Props
     * @property {any} args
     */

    /** @type {Props} */
    let { args } = $props();
    const dispatch = createEventDispatcher();
    let advancedSettings = $state(false);
    let advancedSettingsBody = $state({});
    let newTestName = $state(args.oldTestName);
    let groups = $state();
    let target = $state(args.releaseId);
    let targetRelease = "";
    let group = $state(args.groupId);

    let groupState = $state("targetSelect");
    let validationState = $state("validationCompleted");
    let validated = $state(false);
    let validationMessage = $state("");
    let stateMessages = {
        targetSelect: {
            shown: false,
        },
        groupFetch: {
            shown: true,
            message: "Fetching groups...",
            spinner: true,

        },
        groupsReady: {
            shown: false,
        },
        validationCompleted: {
            shown: false,
        },
        validationProgress: {
            shown: true,
            spinner: true,
            message: "Validating job parameters...",
        }
    };

    const itemizeGroupsForSelect = function (groups) {
        return groups
            .filter(v => v.build_system_id && v.enabled)
            .filter(v => (targetRelease.name || "").toLowerCase().includes("staging") ? true : v.name.toLowerCase().includes("repro"))
            .map((v) => {
                return {
                    value: v.id,
                    label: v.pretty_name ? `${v.pretty_name} [Jenkins path: ${v.build_system_id}]`: `${v.name} [Jenkins path: ${v.build_system_id}]`,
                };
            });
    };

    const fetchCategoriesForTarget = async function(e) {
        try {
            groupState = "groupFetch";
            group = undefined;
            groups = undefined;
            targetRelease = args.targets.find(v => v.id == target);
            const params = {
                targetId: target,
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/jenkins/clone/groups?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            groups = json.response.groups;
            groupState = "groupsReady";

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching groups.\nMessage: ${error.response.arguments[0]}`,
                    "CloneTargetSelector::fetchCategoriesForTarget"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during group fetch",
                    "CloneTargetSelector::fetchCategoriesForTarget"
                );
                console.log(error);
            }
        }
    };

    const fetchOldJobSettings = async function() {
        try {
            const params = {
                buildId: args.buildId,
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/jenkins/clone/settings?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            advancedSettingsBody = json.response;

            return json.response;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching settings.\nMessage: ${error.response.arguments[0]}`,
                    "CloneTargetSelector::fetchOldJobSettings"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during settings fetch",
                    "CloneTargetSelector::fetchOldJobSettings"
                );
                console.log(error);
            }
        }
    };

    const handleValidation = async function(_) {
        try {
            const params = {
                buildId: args.buildId,
                newSettings: advancedSettingsBody,
            };
            validationState = "validationProgress";
            const response = await fetch("/api/v1/jenkins/clone/settings/validate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(params, undefined, 1)
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            validated = json.response.validated;
            validationMessage = json.response.message;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when validating settings.\nMessage: ${error.response.arguments[0]}`,
                    "CloneTargetSelector::handleValidation"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during settings validation",
                    "CloneTargetSelector::handleValidation"
                );
                console.log(error);
            }
        } finally {
            validationState = "validationCompleted";
        }
    };

    const handleClone = function(_) {
        dispatch("exit", {
            newName: newTestName,
            target: target,
            group: group,
            advancedSettings: advancedSettings ? advancedSettingsBody : false,
        });
    };

    onMount(() => {
        if (args.releaseId && args.groupId) {
            fetchCategoriesForTarget();
        }
    });

</script>

<div>
    <div class="mb-2">
        <label class="form-label">Test Name</label>
        <input type="text" class="form-control" bind:value={newTestName}>
    </div>
    <div class="mb-2">
        <label for="" class="form-label">Release</label>
        <select class="form-select" bind:value={target} onchange={fetchCategoriesForTarget}>
            {#each args.targets as release (release.id)}
                {#if release.enabled}
                    <option value="{release.id}">{release.pretty_name ? release.pretty_name: release.name}</option>
                {/if}
            {/each}
        </select>
        <div class="form-text">Specify Argus Release for the cloned test. Usually same release or scylla-staging.</div>
    </div>
    {#if groupState == "groupsReady"}
        <div class="mb-2">
            <label for="" class="form-label">Target group</label>
            <Select items={itemizeGroupsForSelect(groups)} on:select={(e) => group = e.detail.value}/>
            <div class="form-text">Specify Argus Group to store the new test in. [] denotes mapped Jenkins path.</div>
        </div>
    {:else}
        {#if stateMessages[groupState].shown}
            <div>
                {#if stateMessages[groupState].spinner}
                    <span class="spinner-border spinner-border-sm"></span>
                {/if}
                {stateMessages[groupState].message}
            </div>
        {/if}
    {/if}
    <div class="mb-2">
        <div class="form-check form-switch">
            <input type="checkbox" class="form-check-input" bind:checked={advancedSettings}>
            <label type="checkbox" class="form-check-label">Adjust job configuration</label>
        </div>
        {#if validationMessage}
            <div class="alert alert-danger my-2">
                {@html validationMessage}
            </div>
        {/if}
        {#if advancedSettings}
            {#await fetchOldJobSettings()}
                <span class="spinner-border spinner-border-sm"></span> Loading job config...
            {:then settings}
                <div class="mb-1">
                    {#each Object.entries(settings) as [name, _]}
                        <div>
                            <label class="form-label" for="">{JENKINS_ADVANCED_SETTINGS[name]?.label ?? name}</label>
                            <input class="form-control" type="text" name="" id="" bind:value={advancedSettingsBody[name]}>
                        </div>
                        <div class="form-text">{JENKINS_ADVANCED_SETTINGS[name]?.help}</div>
                    {:else}
                        <div>
                            <span class="text-muted">No additional settings to configure.</span>
                        </div>
                    {/each}
                </div>
            {/await}
        {/if}
    </div>
    {#if advancedSettings}
        {#if stateMessages[validationState].shown}
            <div class="mb-2 text-center p-2">
                {#if stateMessages[validationState].spinner}
                    <span class="spinner-border spinner-border-sm"></span>
                {/if}
                {stateMessages[validationState].message}
            </div>
        {/if}
        <div class="mb-2">
            <button
            class="btn btn-primary w-100"
                onclick={handleValidation}
            >
                {#if validated}
                    <Fa icon={faCheck}/>
                {:else if !validated && validationMessage}
                    <Fa icon={faTimes}/>
                {/if}
                Validate
            </button>
        </div>
    {/if}
    <div>
        <button class="btn btn-success w-100" onclick={handleClone} disabled={!(group && target) || (advancedSettings && !validated)}>Next</button>
    </div>
</div>
