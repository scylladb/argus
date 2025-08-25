<script lang="ts">
    import queryString from "query-string";
    import ViewSelectItem from "../AdminPanel/ViewSelectItem.svelte";
    import Select from "svelte-select";
    import { createEventDispatcher } from "svelte";
    import { ADD_ALL_ID } from "../Common/ViewTypes";

    interface Props {
        release: any;
        mode?: string;
        targetType?: string; // can be group, test
    }

    let { release, mode = "single", targetType = "test" }: Props = $props();

    let testSearcherValue = $state();
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
        --item-height="auto"
        --item-line-height="auto"
        id="viewSelectComponent"
        inputAttributes={{ class: "form-control" }}
        bind:value={testSearcherValue}
        placeholder="Type to search. Can be: Test name, Release name, Group name."
        label="name"
        itemId="id"
        loadOptions={testLookup}
        on:select={handleItemSelect}
    >
        <div slot="empty">
            <div class="p-2 text-muted text-center">
                Examples: "release:5.4 artifacts" (any test or group inside 5.4 named artifacts), "group:artifacts centos release:5.3" (tests that contain centos substring inside 5.3 in the artifacts groups), "&lt;test_uuid&gt;" (specific test run id)
            </div>
        </div>
        <div slot="item" let:item let:index>
            <ViewSelectItem {item} />
        </div>
    </Select>
</div>


<style>

</style>
