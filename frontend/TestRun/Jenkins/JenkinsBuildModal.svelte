<script>
    import { createEventDispatcher, onMount } from "svelte";
    import { sendMessage } from "../../Stores/AlertStore";
    import BuildStartPlaceholder from "./BuildStartPlaceholder.svelte";
    import BuildSuccessPlaceholder from "./BuildSuccessPlaceholder.svelte";
    import ParamFetchPlaceholder from "./ParamFetchPlaceholder.svelte";
    import ParameterEditor from "./ParameterEditor.svelte";
    import Fa from "svelte-fa";
    import { faTimes } from "@fortawesome/free-solid-svg-icons";

    export let buildId;
    export let buildNumber;
    let currentState = "none";
    const dispatch = createEventDispatcher();

    const STATES = {
        PARAM_FETCH: "param_fetch",
        PARAM_EDIT: "param_edit",
        BUILD_START: "build_start",
        BUILD_CONFIRMED: "build_confirmed",
    };

    const STATE_MACHINE = {
        [STATES.PARAM_FETCH]: {
            component: ParamFetchPlaceholder,
            onEnter: async function () {
                let res = await fetchLastBuildParams(this.args.buildId, this.args.buildNumber);
                setState(STATES.PARAM_EDIT, {params: res});
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
                params: {}
            },
        },
        [STATES.BUILD_START]: {
            component: BuildStartPlaceholder,
            onEnter: async function () {
                let queueItem = await startJobBuild(this.args.buildParams);
                let event = new CustomEvent("exit", {detail: { queueItem }});
                this.onExit(event);
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
    };

    const setState = function(newState, init) {
        currentState = newState;
        STATE_MACHINE[currentState].args = {...STATE_MACHINE[currentState].args, ...init};
        STATE_MACHINE[currentState].onEnter();
    };

    const fetchLastBuildParams = async function() {
        try {
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
                throw json;
            }

            return json.response.parameters;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching build parameters.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during parameter fetch"
                );
                console.log(error);
            }
        }
    };

    const startJobBuild = async function(buildParams) {
        try {
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
                throw json;
            }

            return json.response.queueItem;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when starting build.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred attempting to start a build"
                );
                console.log(error);
            }
        }
    };

    onMount(() => {
        setState(STATES.PARAM_FETCH, {});
    });
</script>

<div class="build-modal">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 h-50">
            <div class="mb-2 d-flex border-bottom pb-2">
                <h5>Rebuilding <span class="fw-bold">{buildId}#{buildNumber}</span></h5>
                <div class="ms-auto">
                    <button 
                        class="btn btn-close"
                        on:click={() => {
                            dispatch("rebuildCancel");
                        }}
                    ></button>
                </div>
            </div>
            <svelte:component this={STATE_MACHINE[currentState].component} args={STATE_MACHINE[currentState].args} on:exit={STATE_MACHINE[currentState].onExit}/>
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