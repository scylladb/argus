<script lang="ts">
    import sha1 from "js-sha1";
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../Common/DateUtils";
    import { titleCase } from "../Common/TextUtils";
    import { NemesisStatusBackgrounds } from "../Common/TestStatus";
    import NemesisReason from "./NemesisReason.svelte";
    let { nemesisCollection = $bindable([]), resources = [] } = $props();
    let sortHeaders = {
        "startTime": "start_time",
        "endTime": "end_time",
        "status": "status",
        "name": "name",
    };
    let sortHeader = $state("startTime");
    let sortAscending = $state(false);
    let filterString = $state("");

    const filterNemesis = function(nemesis) {
        let nemesisString = `${nemesis.name}${nemesis.target_node.name}${nemesis.status}${timestampToISODate(nemesis.start_time * 1000)}${timestampToISODate(nemesis.end_time * 1000)}`;
        if (filterString == "") {
            return false;
        }
        try {
            return !RegExp(filterString.toLowerCase()).test(nemesisString.toLowerCase());
        } catch (e) {
            return true;
        }
    };

    const sortNemesesByKey = function (nemeses, key, descending) {
        if (key == "node") {
            return nemeses.sort((a, b) => {
                let leftNodeName = a.target_node.name;
                let rightNodeName = b.target_node.name;
                if (leftNodeName > rightNodeName) {
                    return descending ? 1 : -1;
                } else if (rightNodeName > leftNodeName) {
                    return descending ? -1 : 1;
                }
                return 0;
            });
        }
        return Array.from(nemeses).sort((a, b) => {
            if (a[sortHeaders[key]] > b[sortHeaders[key]]) {
                return descending ? 1 : -1;
            } else if (b[sortHeaders[key]] > a[sortHeaders[key]]) {
                return descending ? -1 : 1;
            }
            return 0;
        });
    };

    const createCollapseId = function(nemesis) {
        return sha1(`${nemesis.name}_${nemesis.start_time}_${nemesis.end_time}_${nemesis.target_node.name}`);
    };

    const findAffectedResource = function(nemesis) {
        let resource = resources.find((resource) => resource.name == nemesis.target_node.name) ?? {
            instance_info: {
                private_ip: "#NOT_FOUND",
            },
            state: "#NOT_FOUND"
        };
        return [["Private IP", resource.instance_info.private_ip], ["State", resource.state]];
    };

</script>

<div class="row">
    <div class="col m-2">
        <div class="form-group mb-2">
            <input
                class="form-control"
                type="text"
                placeholder="Filter nemeses"
                onkeyup={(e) => { filterString = e.target.value; nemesisCollection = nemesisCollection; }}
            >
        </div>
        <table class="table table-hover table-bordered">
            <thead>
                    <tr>
                    <th
                        role="button"
                        scope="col"
                        class="text-center align-middle"
                        onclick={() => { sortHeader = "name"; sortAscending = !sortAscending; }}
                    >
                        {#if sortHeader == "name"}
                            <span
                                class="d-inline-block"
                                class:invertArrow={ sortAscending }
                            >
                                &#x25B2;
                            </span>
                        {/if}
                        Nemesis Name
                    </th>
                    <th
                        role="button"
                        scope="col"
                        class="text-center align-middle"
                        onclick={() => { sortHeader = "node"; sortAscending = !sortAscending;  }}
                    >
                        {#if sortHeader == "node"}
                            <span
                                class="d-inline-block"
                                class:invertArrow={ sortAscending }
                            >
                                &#x25B2;
                            </span>
                        {/if}
                        Target node
                    </th>
                    <th
                        role="button"
                        scope="col"
                        class="text-center align-middle"
                        onclick={() => { sortHeader = "status"; sortAscending = !sortAscending;  }}
                    >
                        {#if sortHeader == "status"}
                            <span
                                class="d-inline-block"
                                class:invertArrow={ sortAscending }
                            >
                                &#x25B2;
                            </span>
                        {/if}
                        Status
                    </th>
                    <th
                        role="button"
                        scope="col"
                        class="text-center align-middle"
                        onclick={() => { sortHeader = "startTime"; sortAscending = !sortAscending;  }}
                    >
                        {#if sortHeader == "startTime"}
                            <span
                                class="d-inline-block"
                                class:invertArrow={ sortAscending }
                            >
                                &#x25B2;
                            </span>
                        {/if}
                        Start
                    </th>
                    <th
                        role="button"
                        scope="col"
                        class="text-center align-middle"
                        onclick={() => { sortHeader = "endTime"; sortAscending = !sortAscending;  }}
                    >
                        {#if sortHeader == "endTime"}
                            <span
                                class="d-inline-block"
                                class:invertArrow={ sortAscending }
                            >
                                &#x25B2;
                            </span>
                        {/if}
                        End
                    </th>
                </tr>
            </thead>
            <tbody>
                {#each sortNemesesByKey(nemesisCollection, sortHeader, sortAscending) as nemesis (createCollapseId(nemesis))}
                    <tr
                        class:d-none={filterNemesis(nemesis)}
                    >
                        <td
                            role="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#nemesis{createCollapseId(nemesis)}"
                        >
                            {nemesis.name}
                        </td>
                        <td>
                            {nemesis.target_node.name}
                        </td>
                        <td class="{NemesisStatusBackgrounds[nemesis.status]}">
                            {titleCase(nemesis.status)}
                        </td>
                        <td>{timestampToISODate(nemesis.start_time * 1000, true)}</td>
                        <td>
                            {#if nemesis.end_time != 0}
                                {timestampToISODate(nemesis.end_time * 1000, true)}
                            {:else}
                                In progress...
                            {/if}
                        </td>
                    </tr>
                    <tr class="collapse" id="nemesis{createCollapseId(nemesis)}">
                        <td colspan="5">
                            <h5>Nemesis Information</h5>
                            <ul class="list-unstyled">
                                <li>
                                    <span class="fw-bold">Class:</span> {nemesis.class_name}
                                </li>
                                <li>
                                    <span class="fw-bold">Name:</span> {nemesis.name}
                                </li>
                                <li>
                                    <span class="fw-bold">Status:</span> {titleCase(nemesis.status)}
                                </li>
                                {#if nemesis.duration > 0}
                                <li>
                                    <span class="fw-bold">Duration:</span> {humanizeDuration(nemesis.duration * 1000)}
                                </li>
                                {/if}
                                {#if nemesis.stack_trace}<NemesisReason {nemesis} />{/if}
                            </ul>
                            <h5>Target Information</h5>
                            <ul class="list-unstyled">
                                <li>
                                    <span class="fw-bold">Name:</span> {nemesis.target_node.name}
                                </li>
                                <li>
                                    <span class="fw-bold">Public IP:</span> {nemesis.target_node.ip}
                                </li>
                                {#each findAffectedResource(nemesis) as row}
                                    <li>
                                        <span class="fw-bold">{row[0]}:</span> {row[1]}
                                    </li>
                                {/each}
                                <li>
                                    <span class="fw-bold">Shards:</span> {nemesis.target_node.shards}
                                </li>
                            </ul>
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
</div>

<style>
    .invertArrow {
        transform: rotate(180deg);
    }
</style>
