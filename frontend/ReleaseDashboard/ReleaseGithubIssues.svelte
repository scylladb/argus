<script lang="ts">
    import { v4 as uuidv4 } from 'uuid';
    import { onMount } from "svelte";
    import TestWithIssuesCard from "./TestWithIssuesCard.svelte";
    import { Base64 } from "js-base64";
    import Fa from "svelte-fa";
    import { faExternalLinkSquareAlt } from "@fortawesome/free-solid-svg-icons";
    interface Props {
        release_id?: string;
        tests?: any;
        release_name?: string;
    }

    let { release_id = "", tests = [], release_name = "" }: Props = $props();
    let assortedIssues = $state([]);
    let fetchComplete = $state(false);
    let serializedState = $state(Base64.encode("{}", true));

    const prepareWorkAreaState = function() {
        let state = assortedIssues.reduce((acc, val) => {
            acc[`${release_name}/${val[0].name}`] = {
                runs: [],
                test: val[0].name,
                release: release_name
            };
            console.log(acc);
            return acc;
        }, {});
        return Base64.encode(JSON.stringify(state), true);
    };

    const fetchReleaseIssues = async function () {
        try {
            let apiResponse = await fetch("/api/v1/release/issues", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release_id: release_id,
                    tests: tests,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                assortedIssues = apiJson.response;
                fetchComplete = true;
                serializedState = prepareWorkAreaState();
                console.log(apiJson);
            } else {
                throw apiJson;
            }
        } catch (error) {
            console.log(error);
        }
    };

    onMount(() => {
        fetchReleaseIssues();
    });
</script>

<div class="container-fluid">
    {#if fetchComplete && assortedIssues.length > 0}
        <div class="row hstack">
            <h4>
                Current Issues
            </h4>
            <div>
                <a target="_blank" href="/test_runs?state={serializedState}" class="btn btn-primary">Jump to runs <Fa icon={faExternalLinkSquareAlt}/></a>
            </div>
        </div>
    {/if}
    {#each assortedIssues as testWithIssues}
        <div class="row p-2 bg-white">
            <TestWithIssuesCard test={testWithIssues[0]} issues={testWithIssues[1]}/>
        </div>
    {:else}
        <div class="row p-2">
            <p class="text-muted text-center">
                {#if fetchComplete}
                    No Issues so far! You can help by creating one...
                {:else}
                    Loading...
                {/if}
            </p>
        </div>
    {/each}
</div>
