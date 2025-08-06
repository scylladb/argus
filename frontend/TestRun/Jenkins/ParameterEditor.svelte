<script>
    import { createEventDispatcher } from "svelte";
    import { sanitizeSelector } from "../../Common/TextUtils";
    import SctParameterWizard from "./SCTParameterWizard.svelte";
    import WizardUnavailable from "./WizardUnavailable.svelte";
    import { sendMessage } from "../../Stores/AlertStore";


    /**
     * @typedef {Object} Props
     * @property {{params: {_class: string, name: string, value: string, description: string}[]}} args
     */

    /** @type {Props} */
    let { args } = $props();

    const WIZARDS = {
        "scylla-cluster-tests": SctParameterWizard,
        unsupported: WizardUnavailable,
    };


    let wizard = $state();
    let paramTab = $state(0);
    let buildParams = $state(args.params.reduce((acc, val) => {
        acc[val.name] = val.value;
        return acc;
    }, {}));
    const dispatch = createEventDispatcher();


    const handleParameterSubmit = function (_) {
        if (wizard && wizard.validate) {
            let [validated, errors] = wizard.validate();
            if (!validated) {
                sendMessage("error", "Validation failed. Please verify the parameters", "ParameterEditor::Validate");
                return;
            }
        }
        dispatch("exit", { buildParams: buildParams });
    };
</script>

<div>
    <div class="mb-1">
        <div class="btn-group btn-group-sm" role="group">
            <button
                type="button"
                class="btn"
                class:btn-primary={paramTab == 0}
                class:btn-outline-primary={paramTab != 0}
                onclick={() => (paramTab = 0)}
            >Wizard</button>
            <button
                type="button"
                class="btn"
                class:btn-primary={paramTab == 1}
                class:btn-outline-primary={paramTab != 1}
                onclick={() => (paramTab = 1)}
            >This build parameters</button>
            <button
                type="button"
                class="btn"
                class:btn-primary={paramTab == 2}
                class:btn-outline-primary={paramTab != 2}
                onclick={() => (paramTab = 2)}
            >All parameters</button>
        </div>
    </div>
    <div class="mb-2">
        {#if paramTab == 0}
            {@const SvelteComponent = WIZARDS[args.pluginName] ?? WIZARDS.unsupported}
            <SvelteComponent bind:this={wizard} params={buildParams} rawParams={args.params}/>
        {:else}
            {#each args.params as param}
                {#if param.value || paramTab == 2}
                    <div class="mb-1">
                        <label class="form-label fw-bold" for={param.name}>{param.name}</label>
                         {#if (param._class || "").includes("TextParameter")}
                            <textarea class="form-control" id={param.name} bind:value={buildParams[param.name]} rows="4"></textarea>
                        {:else}
                            <input class="form-control" id={param.name} type="text" bind:value={buildParams[param.name]}>
                        {/if}
                        <div id="paramHelp{sanitizeSelector(param.name)}" class="form-text">{@html param.description}</div>
                    </div>
                {/if}
            {/each}
        {/if}
    </div>
    <div class="text-end">
        <button
            class="btn btn-success w-100 mb-1"
            onclick={handleParameterSubmit}
        >Build</button>
    </div>
</div>
