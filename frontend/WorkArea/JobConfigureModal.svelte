<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import queryString from "query-string";
    import { JENKINS_ADVANCED_SETTINGS } from "../Common/JenkinsSettingsHelp";
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    let { buildId, testName } = $props();
    let settings = $state();
    let failed = $state(false);
    let failMessage = $state("");
    let validationState = "validationCompleted";
    let validated = $state(false);
    let validationMessage = $state("");
    let innerWidth = $state(1024);
    let smallScreen = $derived(innerWidth < 768);
    const dispatch = createEventDispatcher();

    function handleKeyDown(event) {
        if (event.key === "Escape") {
            dispatch("configureCancel");
        }
    }

    const fetchOldJobSettings = async function() {
        try {
            const params = {
                buildId: buildId,
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/jenkins/clone/settings?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            settings = json.response;

            return json.response;
        } catch (error) {
            failed = true;
            failMessage = error.response ? `An error occured when fetching settings: ${error.response.arguments[0]}` : `An error occured when fetching settings: ${error}`;
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching settings.\nMessage: ${error.response.arguments[0]}`,
                    "JobConfigureModal::fetchOldJobSettings"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during settings fetch",
                    "JobConfigureModal::fetchOldJobSettings"
                );
                console.log(error);
            }
        }
    };

    const handleValidation = async function(_) {
        try {
            const params = {
                buildId: buildId,
                newSettings: settings,
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
                    "JobConfigureModal::handleValidation"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during settings validation",
                    "JobConfigureModal::handleValidation"
                );
                console.log(error);
            }
        } finally {
            validationState = "validationCompleted";
        }
    };

    const handleSettingsChange = async function () {
        try {
            const params = {
                buildId: buildId,
                settings: settings,
            };
            const response = await fetch("/api/v1/jenkins/clone/settings/change",{
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(params)
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            sendMessage("success", `Settings changed successfuly for job ${buildId}!`, "JobConfigureModal::handleSettingsChange");
            dispatch("settingsFinished");

            return json.response;
        } catch (error) {
            failed = true;
            failMessage = error.response ? `An error occured when changing settings: ${error.response.arguments[0]}` : `An error occured when changing settings: ${error}`;
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching settings.\nMessage: ${error.response.arguments[0]}`,
                    "JobConfigureModal::handleSettingsChange"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during settings fetch",
                    "JobConfigureModal::handleSettingsChange"
                );
                console.log(error);
            }
        }
    };

    onMount(fetchOldJobSettings);
</script>

<svelte:window bind:innerWidth onkeydown={handleKeyDown} />
<div class="build-modal">
    <div class="d-flex align-items-center justify-content-center p-2 p-md-4">
        <div class="rounded bg-white p-3 p-md-4 {smallScreen ? 'modal-panel-mobile' : 'modal-panel'}">
            <div class="mb-2 d-flex border-bottom pb-2 min-width-0">
                <h5 class="text-truncate mb-0">Configuring <span class="fw-bold">{testName}</span></h5>
                <div class="ms-auto flex-shrink-0">
                    <button
                        class="btn btn-close"
                        onclick={() => {
                            dispatch("configureCancel");
                        }}
                    ></button>
                </div>
            </div>
            <div>
                {#if failed}
                    <div class="mb-1 alert alert-danger">
                        {failMessage}
                    </div>
                {:else if settings}
                    {#if validationMessage}
                        <div class="alert alert-danger my-2">
                            {@html validationMessage}
                        </div>
                    {/if}
                    <div class="mb-1">
                        {#each Object.entries(settings) as [name, _]}
                            <div>
                                <label class="form-label" for="">{JENKINS_ADVANCED_SETTINGS[name]?.label ?? name}</label>
                                <input class="form-control" type="text" name="" id="" bind:value={settings[name]}>
                            </div>
                            <div class="form-text">{JENKINS_ADVANCED_SETTINGS[name]?.help}</div>
                        {:else}
                            <div>
                                <span class="text-muted">No additional settings to configure.</span>
                            </div>
                        {/each}
                    </div>
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
                    <div>
                        <button class="btn btn-success w-100" onclick={handleSettingsChange} disabled={!validated}>Next</button>
                    </div>
                {:else}
                    <div>
                        <span class="spinner-border spinner-border-sm"></span> Loading settings...
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>

<style>
    .modal-panel {
        width: 50%;
    }
    .modal-panel-mobile {
        width: 100%;
    }
    .min-width-0 {
        min-width: 0;
    }
    .build-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }
</style>
