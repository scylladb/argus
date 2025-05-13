<script>
    import queryString from "query-string";
    import ViewSelectItem from "../AdminPanel/ViewSelectItem.svelte";
    import Select from "svelte-select";
    import { createEventDispatcher } from "svelte";
    import { ADD_ALL_ID } from "../Common/ViewTypes";

    export let release;
    export let mode = "single";
    export let targetType = "test"; // can be group, test

    let testSearcherValue;
    let lastHits = [];
    let items = [];
    const dispatch = createEventDispatcher();

    /**
     * @param {string} query
     */
    const testLookup = async function (query) {
        try {
            const params = {
                query: query,
                releaseId: release ?  release.id : null,
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/planning/search?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            lastHits = json.response.hits;
            return json.response.hits
                .slice(0, 100)
                .filter(e => targetType ? e.type == targetType : true)
                .filter(e => mode == "single" ? e.id != ADD_ALL_ID : true);

        } catch (error) {
            console.log(error);
        }
    };

    const handleAllItemSelect = function() {
        if (mode == "single") return;
        items = [
            ...items,
            ...lastHits
                .filter(i => i.id != ADD_ALL_ID
                ).map(item => {
                    return {
                        name: item.pretty_name || item.name,
                        release: item.release?.name,
                        group: item.group?.pretty_name || item.group?.name,
                        type: item.type,
                        id: item.id,
                    };
                })];
        testSearcherValue = undefined;
    };

    const handleItemSelect = function(e) {
        const item = e.detail;
        if (item.id == ADD_ALL_ID) return handleAllItemSelect();
        items = [...items, {
            name: item.pretty_name || item.name,
            release: item.release?.name,
            group: item.group?.pretty_name || item.group?.name,
            test: item.test?.name,
            testId: item.test?.id,
            groupId: item.group?.id,
            releaseId: item.release?.id,
            type: item.type,
            id: item.id,

        }];
        testSearcherValue = undefined;
        if (mode == "single") handleFinishSearch();
    };

    const handleFinishSearch = function () {
        dispatch("selected", {
            items: items,
        });
        items = [];
    };

</script>

<div class="">
    <Select
        id="viewSelectComponent"
        inputAttributes={{ class: "form-control" }}
        bind:value={testSearcherValue}
        placeholder="Type to search. Can be: Test name, Release name, Group name."
        noOptionsMessage='Examples: "release:5.4 artifacts" (any test or group inside 5.4 named artifacts), "group:artifacts centos release:5.3" (tests that contain centos substring inside 5.3 in the artifacts groups), "<test_uuid>" (specific test run id)'
        labelIdentifier="name"
        optionIdentifier="id"
        Item={ViewSelectItem}
        loadOptions={testLookup}
        on:select={handleItemSelect}
    />
</div>


<style>

</style>
