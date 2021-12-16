<script>
    import Fa from "svelte-fa";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import { createEventDispatcher } from "svelte";
    import { Base64 } from "js-base64";
    import {
        faCircle,
        faTrash,
        faExternalLinkSquareAlt,
    } from "@fortawesome/free-solid-svg-icons";
    export let tests = [];
    export let releaseName = "";
    let encodedState = "e30";
    $: encodedState = Base64.encode(
        JSON.stringify(
            tests.reduce((acc, val) => {
                acc[`${releaseName}/${val.name}`] = {
                    test: val.name,
                    release: releaseName,
                    runs: [],
                };
                return acc;
            }, {})
        ),
        true
    );
    const dispatch = createEventDispatcher();
    const handleTrashClick = function (name) {
        dispatch("deleteRequest", {
            name: name,
        });
    };
</script>

{#if tests.length > 0}
    <div class="d-flex flex-column">
        <ul class="list-group" style="height: 378px; overflow-y: scroll;">
            {#each tests as test (test.name)}
                <li class="list-group-item d-flex align-items-center">
                    <div class="{StatusCSSClassMap[test.status]} me-3">
                        <Fa icon={faCircle} />
                    </div>
                    <div class="d-flex flex-column">
                        <span>{test.name}</span>
                        <span class="text-muted" style="font-size: 0.75em"
                            >{new Date(
                                test.start_time * 1000
                            ).toLocaleString()}</span
                        >
                    </div>
                    <button
                        class="ms-auto btn btn-danger btn-sm"
                        on:click={() => handleTrashClick(test.name)}
                        ><Fa icon={faTrash} /></button
                    >
                </li>
            {/each}
        </ul>
        <a
            href="/run_dashboard?state={encodedState}"
            class="btn btn-primary"
            target="_blank"
            >Open work area <Fa icon={faExternalLinkSquareAlt} /></a
        >
    </div>
{/if}

<style>
</style>
