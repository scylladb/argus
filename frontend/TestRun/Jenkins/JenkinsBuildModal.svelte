<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import BuildStartPlaceholder from "./BuildStartPlaceholder.svelte";
    import BuildSuccessPlaceholder from "./BuildSuccessPlaceholder.svelte";
    import ParamFetchPlaceholder from "./ParamFetchPlaceholder.svelte";
    import ParameterEditor from "./ParameterEditor.svelte";
    import ModalError from "./ModalError.svelte";
    import BuildConfirmationDialog from "./BuildConfirmationDialog.svelte";

    let { buildId, buildNumber, pluginName } = $props();
    let currentState = $state("none");
    const dispatch = createEventDispatcher();

    const STATES = {
        PARAM_FETCH: "param_fetch",
        PARAM_EDIT: "param_edit",
        BUILD_START: "build_start",
        BUILD_CONFIRMED: "build_confirmed",
        BUILD_CONFIRM: "build_confirmation",
        ERROR: "error",
    };

    const STATE_MACHINE = $state({
        [STATES.PARAM_FETCH]: {
            component: ParamFetchPlaceholder,
            onEnter: async function () {
                try {
                    let res = await fetchLastBuildParams(this.args.buildId, this.args.buildNumber);
                    setState(STATES.PARAM_EDIT, {params: res});
                } catch (error) {
                    if (error.message == "#noBuildsAvailable") {
                        setState(STATES.BUILD_CONFIRM);
                    } else {
                        setState(STATES.ERROR, { message: error.message });
                        console.log(error);
                    }
                }
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                //empty
            },
            args: {
                buildId: buildId,
                buildNumber: buildNumber,
            },
        },
        [STATES.PARAM_EDIT]: {
            component: ParameterEditor,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                console.log(event.detail);
                setState(STATES.BUILD_START, { buildParams: event.detail.buildParams });
            },
            args: {
                pluginName: pluginName,
                params: {}
            },
        },
        [STATES.BUILD_CONFIRM]: {
            component: BuildConfirmationDialog,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (e) {
                if (e.detail.confirm) {
                    setState(STATES.BUILD_START, { buildParams: {} });
                } else {
                    dispatch("rebuildCancel");
                }
            },
            args: {
            },
        },
        [STATES.BUILD_START]: {
            component: BuildStartPlaceholder,
            onEnter: async function () {
                try {
                    let queueItem = await startJobBuild(this.args.buildParams);
                    let event = new CustomEvent("exit", {detail: { queueItem }});
                    this.onExit(event);
                } catch (error) {
                    setState(STATES.ERROR, { message: error.message });
                    console.log(error);
                }
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                setState(STATES.BUILD_CONFIRMED, {queueItem: event.detail.queueItem});
            },
            args: {
                buildParams: {},
            },
        },
        [STATES.BUILD_CONFIRMED]: {
            component: BuildSuccessPlaceholder,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                dispatch("rebuildComplete");
            },
            args: {
                queueItem: -1,
            },
        },
        [STATES.ERROR]: {
            component: ModalError,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                //empty
            },
            args: {
                message: "",
            },
        },
        none: {
            component: undefined,
            onEnter: () => {
                //empty
            },
            onExit: () => {
                //empty
            },
            args: {},
        }
    });

    const setState = function(newState, init) {
        currentState = newState;
        STATE_MACHINE[currentState].args = {...STATE_MACHINE[currentState].args, ...init};
        STATE_MACHINE[currentState].onEnter();
    };

    const fetchLastBuildParams = async function() {
        const params = {
            buildId: buildId,
            buildNumber: Number.parseInt(buildNumber),
        };
        const response = await fetch("/api/v1/jenkins/params", {
            headers: {
                "Content-Type": "application/json",
            },
            method: "POST",
            body: JSON.stringify(params),
        });

        const json = await response.json();
        if (json.status != "ok") {
            throw new Error(json.response.arguments[0]);
        }

        return json.response.parameters;
    };

    const startJobBuild = async function(buildParams) {
        const params = {
            buildId: buildId,
            parameters: buildParams,
        };
        const response = await fetch("/api/v1/jenkins/build", {
            headers: {
                "Content-Type": "application/json",
            },
            method: "POST",
            body: JSON.stringify(params),
        });

        const json = await response.json();
        if (json.status != "ok") {
            throw new Error(json.response.arguments[0]);
        }

        return json.response.queueItem;
    };

    onMount(() => {
        setState(STATES.PARAM_FETCH, {});
    });

    const SvelteComponent = $derived(STATE_MACHINE[currentState].component);
</script>

<div class="build-modal">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 h-50">
            <div class="mb-2 d-flex border-bottom pb-2">
                {#if buildNumber}
                    <h5>Rebuilding <span class="fw-bold">{buildId}#{buildNumber}</span></h5>
                {:else}
                    <h5>Starting <span class="fw-bold">{buildId}</span></h5>
                {/if}
                <div class="ms-auto">
                    <button
                        class="btn btn-close"
                        onclick={() => {
                            dispatch("rebuildCancel");
                        }}
                    ></button>
                </div>
            </div>
            <SvelteComponent args={STATE_MACHINE[currentState].args} on:exit={STATE_MACHINE[currentState].onExit}/>
        </div>
    </div>
</div>

<style>
    .h-50 {
        width: 50%;
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
