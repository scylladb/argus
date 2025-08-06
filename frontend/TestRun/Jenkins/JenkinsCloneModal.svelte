<script lang="ts">
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
    import ModalError from "./ModalError.svelte";
    import CloneSuccess from "./CloneSuccess.svelte";

    let {
        buildId,
        buildNumber,
        pluginName,
        testId,
        oldTestName,
        releaseId,
        groupId
    } = $props();
    let newBuildId;
    let newTestId;
    let shouldRestartFromParams = false;

    let currentState = $state("none");
    const dispatch = createEventDispatcher();

    const STATES = {
        LOAD_TARGETS: "load_targets",
        CLONE_EDITOR: "clone_editor",
        CLONE_CREATE: "clone_create",
        CLONE_SUCCESS: "clone_success",
        JOB_FETCH: "job_fetch",
        JOB_EDIT: "job_edit",
        JOB_COMMIT: "job_commit",
        PARAM_FETCH: "param_fetch",
        PARAM_EDIT: "param_edit",
        BUILD_START: "build_start",
        BUILD_CONFIRMED: "build_confirmed",
        ERROR: "error",
    };

    const STATE_MACHINE = $state({
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
                try {
                    let res = await cloneJob(this);
                    setState(STATES.CLONE_SUCCESS, {result: res});
                } catch (error) {
                    setState(STATES.ERROR, { message: error.message });
                    console.log(error);
                }
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
        [STATES.CLONE_SUCCESS]: {
            component: CloneSuccess,
            onEnter: async function () {
                //empty
            },
            /**
             * @param {CustomEvent} event
             */
            onExit: async function (event) {
                newBuildId = event.detail.newBuildId;
                newTestId = event.detail.newTestId;
                if (buildNumber == -1) {
                    shouldRestartFromParams = true;
                    setState(STATES.BUILD_START, { buildParams: {}});
                } else {
                    setState(STATES.PARAM_FETCH, {});
                }
            },
            args: {
                result: undefined,
            },
        },
        [STATES.PARAM_FETCH]: {
            component: ParamFetchPlaceholder,
            onEnter: async function () {
                try {
                    let res = await fetchLastBuildParams(this.args.buildId, this.args.buildNumber);
                    setState(STATES.PARAM_EDIT, {params: res});
                } catch (error) {
                    setState(STATES.ERROR, { message: error.message });
                    console.log(error);
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
                setState(STATES.BUILD_START, { buildParams: event.detail.buildParams, firstBuildRestart: shouldRestartFromParams });
            },
            args: {
                pluginName: pluginName,
                params: {}
            },
        },
        [STATES.BUILD_START]: {
            component: BuildStartPlaceholder,
            onEnter: async function () {
                try {
                    let queueItem = await startJobBuild(newBuildId, this.args.buildParams);
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
                    if (shouldRestartFromParams) {
                        setState(STATES.PARAM_FETCH, { buildId: newBuildId, buildNumber: event.detail?.buildNumber ?? 1 });
                    } else {
                        setState(STATES.BUILD_START, {firstBuildRestart: true});
                    }
                } else {
                    dispatch("cloneComplete", { testId: newTestId });
                }
            },
            args: {
                queueItem: -1,
                isFirst: false,
                plugin: null,
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

    const fetchLastBuildParams = async function(buildId, buildNumber) {
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

    const getCloneTargets = async function(testId) {
        const params = {
            testId: testId,
        };
        let qs = queryString.stringify(params);
        const response = await fetch("/api/v1/jenkins/clone/targets?" + qs);

        const json = await response.json();
        if (json.status != "ok") {
            throw new Error(json.response.arguments[0]);
        }

        return json.response.targets;
    };

    /**
     *
     * @param {{
     * args: {
     *  currentTestId: string,
     *  newName: string,
     *  target: string,
     *  group: string,
     *  advancedSettings: boolean | { [string]: string },
     * }
     * }} state
     */
    const cloneJob = async function(state) {
        const response = await fetch("/api/v1/jenkins/clone/create", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(state.args),
        });

        const json = await response.json();
        if (json.status != "ok") {
            throw new Error(json.response.arguments[0]);
        }

        return json.response;
    };


    onMount(() => {
        setState(STATES.LOAD_TARGETS, {});
    });

    const SvelteComponent = $derived(STATE_MACHINE[currentState].component);
</script>

<div class="clone-modal">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 h-50">
            <div class="mb-2 d-flex border-bottom pb-2">
                {#if buildNumber != -1}
                    <h5>Cloning <span class="fw-bold">{buildId}#{buildNumber}</span></h5>
                {:else}
                    <h5>Cloning <span class="fw-bold">{buildId}</span></h5>
                {/if}
                <div class="ms-auto">
                    <button
                        class="btn btn-close"
                        onclick={() => {
                            dispatch("cloneCancel");
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
