<script>
    import { createEventDispatcher, onMount } from "svelte";
    import { sendMessage } from "../../Stores/AlertStore";
    import BuildStartPlaceholder from "./BuildStartPlaceholder.svelte";
    import BuildSuccessPlaceholder from "./BuildSuccessPlaceholder.svelte";
    import ParamFetchPlaceholder from "./ParamFetchPlaceholder.svelte";
    import ParameterEditor from "./ParameterEditor.svelte";
    import LoadTargetsPlaceholder from "./LoadTargetsPlaceholder.svelte";
    import CloneTargetSelector from "./CloneTargetSelector.svelte";
    import CloneCreatePlaceholder from "./CloneCreatePlaceholder.svelte";
    import queryString from "query-string";
    import { startJobBuild } from "./Build";

    export let buildId;
    export let buildNumber;
    export let pluginName;
    export let testId;
    export let oldTestName;
    export let releaseId;
    export let groupId;
    let newBuildId;

    let currentState = "none";
    const dispatch = createEventDispatcher();

    const STATES = {
        LOAD_TARGETS: "load_targets",
        CLONE_EDITOR: "clone_editor",
        CLONE_CREATE: "clone_create",
        JOB_FETCH: "job_fetch",
        JOB_EDIT: "job_edit",
        JOB_COMMIT: "job_commit",
        PARAM_FETCH: "param_fetch",
        PARAM_EDIT: "param_edit",
        BUILD_START: "build_start",
        BUILD_CONFIRMED: "build_confirmed",
    };

    const STATE_MACHINE = {
        [STATES.LOAD_TARGETS]: {
            component: LoadTargetsPlaceholder,
            onEnter: async function () {
                let res = await getCloneTargets(this.args.testId);
                setState(STATES.CLONE_EDITOR, {targets: res});
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                //empty
            },
            args: {
                testId: testId,
            },
        },
        [STATES.CLONE_EDITOR]: {
            component: CloneTargetSelector,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                setState(STATES.CLONE_CREATE, {
                    newName: event.detail.newName,
                    target: event.detail.target,
                    group: event.detail.group,
                    advancedSettings: event.detail.advancedSettings,
                });
            },
            args: {
                releaseId: releaseId,
                groupId: groupId,
                buildId: buildId,
                pluginName: pluginName,
                oldTestName: oldTestName,
                targets: [],
            },
        },
        [STATES.CLONE_CREATE]: {
            component: CloneCreatePlaceholder,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                newBuildId = event.detail.newBuildId;
                setState(STATES.PARAM_FETCH, {});
            },
            args: {
                currentTestId: testId,
                newName: "",
                target: "",
                group: "",
                advancedSettings: false,
            },
        },
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
                pluginName: pluginName,
                params: {}
            },
        },
        [STATES.BUILD_START]: {
            component: BuildStartPlaceholder,
            onEnter: async function () {
                let queueItem = await startJobBuild(newBuildId, this.args.buildParams);
                let event = new CustomEvent("exit", {detail: { queueItem }});
                this.onExit(event);
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                setState(STATES.BUILD_CONFIRMED, {queueItem: event.detail.queueItem, isFirst: !this.args.firstBuildRestart, plugin: pluginName});
            },
            args: {
                buildParams: {},
                firstBuildRestart: false,
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
                if (event.detail?.firstBuildRestart) {
                    setState(STATES.BUILD_START, {firstBuildRestart: true});
                } else {
                    dispatch("cloneComplete");
                }
            },
            args: {
                queueItem: -1,
                isFirst: false,
                plugin: null,
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

    const getCloneTargets = async function(testId) {
        try {
            const params = {
                testId: testId,
            };
            let qs = queryString.stringify(params);
            const response = await fetch("/api/v1/jenkins/clone/targets?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            return json.response.targets;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching clone targets.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during clone target fetch"
                );
                console.log(error);
            }
        }
    };


    onMount(() => {
        setState(STATES.LOAD_TARGETS, {});
    });
</script>

<div class="clone-modal">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 h-50">
            <div class="mb-2 d-flex border-bottom pb-2">
                <h5>Cloning <span class="fw-bold">{buildId}#{buildNumber}</span></h5>
                <div class="ms-auto">
                    <button 
                        class="btn btn-close"
                        on:click={() => {
                            dispatch("cloneCancel");
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
    .clone-modal {
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