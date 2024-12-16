<script>
    export let resources;
    export let backend;
    export let run_id;
    import { timestampToISODate } from "../Common/DateUtils";
    import { titleCase } from "../Common/TextUtils";
    import Fa from "svelte-fa";
    import {
        faCopy,
        faPlay,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    let sortHeaders = {
        creationTime: ["instance_info", "creation_time"],
        terminationTime: ["instance_info", "termination_time"],
        terminationReason: ["instance_info", "termination_reason"],
        region: ["instance_info", "region"],
        dcName: ["instance_info", "dc_name"],
        rackName: ["instance_info", "rack_name"],
        provider: ["instance_info", "provider"],
        state: "state",
        name: "name",
        shards: ["instance_info", "shards_amount"],
        publicIp: ["instance_info", "public_ip"],
        privateIp: ["instance_info", "private_ip"],
    };
    let sortHeader = "name";
    let sortAscending = false;
    let filterString = "";

    const tableStates = {
        running: "table-success",
        stopped: "table-",
        terminated: "table-danger",
    };

    let regions = "SCT_REGION_NAME= SCT_GCE_DATACENTER= SCT_AZURE_REGION_NAME= ";
    const CMD_CLEAN_RESOURCES = `${regions} hydra clean-resources --backend ${backend} --test-id ${run_id}`;

    const filterResource = function (resource) {
        let resourceAsString = `${resource.name}${resource.state}${
            resource.instance_info.shards_amount
        }${timestampToISODate(
            resource.instance_info.creation_time * 1000
        )}${timestampToISODate(
            resource.instance_info.termination_time * 1000
        )}${resource.instance_info.termination_reason}`;
        if (filterString == "") {
            return false;
        }
        try {
            return !RegExp(filterString.toLowerCase()).test(
                resourceAsString.toLowerCase()
            );
        } catch (e) {
            return true;
        }
    };

    const sortResourcesByKey = function (resources, key, descending) {
        const getValue = function (resource, key) {
            let path = sortHeaders[key];
            if (typeof path == "string") {
                let value = resource[sortHeaders[path]];
                return value;
            } else if (typeof path == "object") {
                let value = resource;
                for (let idx = 0; idx < path.length; idx++) {
                    value = value[path[idx]];
                }
                return value;
            }
        };

        return resources.sort((a, b) => {
            if (getValue(a, key) > getValue(b, key)) {
                return descending ? 1 : -1;
            } else if (getValue(b, key) > getValue(a, key)) {
                return descending ? -1 : 1;
            }
            return 0;
        });
    };
</script>
<div class="row">
    <div class="p-1 m-2 d-flex align-items-center">
        <button
            type="button"
            class="btn btn-outline-success me-2"
            on:click={() => {
                navigator.clipboard.writeText(
                    CMD_CLEAN_RESOURCES
                );
                sendMessage("success", `\`${CMD_CLEAN_RESOURCES}\` has been copied to your clipboard`);
            }}>
            <Fa icon={faCopy} /> Hydra Clean Resources
        </button>
        <a
            href="https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-clean-test-resources/parambuild/?test_id={run_id}&backend={backend}"
            class="btn btn-outline-primary"
            target="_blank"
            aria-current="page">
            <Fa icon={faPlay} /> Clean with jenkins
        </a>
    </div>
</div>
<div class="form-group mb-2">
    <input
        class="form-control"
        type="text"
        placeholder="Filter resources"
        on:keyup={(e) => {
            filterString = e.target.value;
            resources = resources;
        }}
    />
</div>
<table class="table table-bordered border">
    <thead>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "provider";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "provider"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Provider
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "name";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "name"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Resource name
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "region";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "region"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Region
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "dcName";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "dcName"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            DC Name
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "rackName";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "rackName"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Rack Name
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "shards";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "shards"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Shards
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "publicIp";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "publicIp"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Public IP
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "privateIp";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "privateIp"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Private IP
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "state";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "state"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            State
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "creationTime";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "creationTime"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Created at
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "terminationTime";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "terminationTime"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Terminated at
        </th>
        <th
            role="button"
            scope="col"
            class="text-center align-middle"
            on:click={() => {
                sortHeader = "terminationReason";
                sortAscending = !sortAscending;
            }}
        >
            {#if sortHeader == "terminationReason"}
                <span
                    class="d-inline-block"
                    class:invertArrow={sortAscending}
                >
                    &#x25B2;
                </span>
            {/if}
            Termination reason
        </th>
    </thead>
    <tbody>
        {#each sortResourcesByKey(resources, sortHeader, sortAscending) as resource (resource.name)}
            <tr class:d-none={filterResource(resource)}>
                <td>{resource.instance_info.provider}</td>
                <td>{resource.name}</td>
                <td>{resource.instance_info.region}</td>
                <td>{resource.instance_info.dc_name ?? ""}</td>
                <td>{resource.instance_info.rack_name ?? ""}</td>
                <td>{resource.instance_info.shards_amount}</td>
                <td>
                    {resource.instance_info.public_ip}
                </td>
                <td>
                    {resource.instance_info.private_ip}
                </td>
                <td
                    class="{tableStates[resource.state]}"
                >
                {titleCase(resource.state)}
                </td>
                <td>{timestampToISODate(resource.instance_info.creation_time * 1000, true)}</td>
                <td>
                    {#if resource.instance_info.termination_time > 0}
                        {timestampToISODate(resource.instance_info.termination_time * 1000, true)}
                    {:else}
                        <!-- Still running -->
                    {/if}
                </td>
                <td class="narrow-cell">{resource.instance_info.termination_reason}</td>
            </tr>
        {:else}
            <tr>
                <td colspan="10"> No resources </td>
            </tr>
        {/each}
    </tbody>
</table>

<style>
    .invertArrow {
        transform: rotate(180deg);
    }

    .narrow-cell {
        max-width: 384px;
    }
</style>
