<script>
    export let resources;
    import { timestampToISODate } from "../Common/DateUtils";
    import { titleCase } from "../Common/TextUtils";
    let sortHeaders = {
        creationTime: ["instance_info", "creation_time"],
        terminationTime: ["instance_info", "termination_time"],
        terminationReason: ["instance_info", "termination_reason"],
        state: "state",
        name: "name",
        shards: ["instance_info", "shards_amount"],
    };
    let sortHeader = "name";
    let sortAscending = false;
    let filterString = "";

    const tableStates = {
        running: "table-success",
        stopped: "table-",
        terminated: "table-danger",
    };

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
            if (typeof path == 'string') {
                let value = resource[sortHeaders[path]];
                return value;
            } else if (typeof path == 'object') {
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
                <td>{resource.name}</td>
                <td>{resource.instance_info.shards_amount}</td>
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
                <td colspan="6"> No resources </td>
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
