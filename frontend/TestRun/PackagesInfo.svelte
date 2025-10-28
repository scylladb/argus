<script lang="ts">
    let { packages = $bindable() } = $props();
    let sortHeaders = {
        date: "date",
        revisionId: "revision_id",
        buildId: "build_id",
        version: "version",
        name: "name",
    };
    let sortHeader = $state("name");
    let sortAscending = $state(false);
    let filterString = $state("");


    const filterColumn = function (pkg) {
        let pkgAsString = `${pkg.name}${pkg.version}${pkg.build_id}${pkg.revision_id}${pkg.date}`;
        if (filterString == "") {
            return false;
        }
        try {
            return !RegExp(filterString.toLowerCase()).test(
                pkgAsString.toLowerCase()
            );
        } catch (e) {
            return true;
        }
    };

    const getPackageKey = function (pkg, idx) {
        // Include the index to guarantee uniqueness when API returns duplicated package rows
        return [
            pkg?.name ?? "unknown",
            pkg?.version ?? "unknown",
            pkg?.build_id ?? "no-build",
            pkg?.revision_id ?? "no-revision",
            idx
        ].join("|");
    };

    const sortPackagesByKey = function (packages, key, descending) {
        const data = packages ?? [];
        const getValue = function (pkg, key) {
            let path = sortHeaders[key];
            if (typeof path == "string") {
                let value = pkg[sortHeaders[path]];
                return value;
            } else if (typeof path == "object") {
                let value = pkg;
                for (let idx = 0; idx < path.length; idx++) {
                    value = value[path[idx]];
                }
                return value;
            }
        };

        // Create a new array to avoid mutating the original
        return [...data].sort((a, b) => {
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
        placeholder="Filter packages"
        onkeyup={(e) => {
            filterString = e.target.value;
            packages = packages;
        }}
    />
</div>
<table class="table table-bordered border">
    <thead>
        <tr>
            <th
                role="button"
                scope="col"
                class="text-center align-middle"
                onclick={() => {
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
                Name
            </th>
            <th
                role="button"
                scope="col"
                class="text-center align-middle"
                onclick={() => {
                    sortHeader = "version";
                    sortAscending = !sortAscending;
                }}
            >
                {#if sortHeader == "version"}
                    <span
                        class="d-inline-block"
                        class:invertArrow={sortAscending}
                    >
                        &#x25B2;
                    </span>
                {/if}
                Version
            </th>
            <th
                role="button"
                scope="col"
                class="text-center align-middle"
                onclick={() => {
                    sortHeader = "date";
                    sortAscending = !sortAscending;
                }}
            >
                {#if sortHeader == "date"}
                    <span
                        class="d-inline-block"
                        class:invertArrow={sortAscending}
                    >
                        &#x25B2;
                    </span>
                {/if}
                Date
            </th>
            <th
                role="button"
                scope="col"
                class="text-center align-middle"
                onclick={() => {
                    sortHeader = "buildId";
                    sortAscending = !sortAscending;
                }}
            >
                {#if sortHeader == "buildId"}
                    <span
                        class="d-inline-block"
                        class:invertArrow={sortAscending}
                    >
                        &#x25B2;
                    </span>
                {/if}
                Build ID
            </th>
            <th
                role="button"
                scope="col"
                class="text-center align-middle"
                onclick={() => {
                    sortHeader = "revisionId";
                    sortAscending = !sortAscending;
                }}
            >
                {#if sortHeader == "revisionId"}
                    <span
                        class="d-inline-block"
                        class:invertArrow={sortAscending}
                    >
                        &#x25B2;
                    </span>
                {/if}
                SCM Revision
            </th>
        </tr>
    </thead>
    <tbody>
        {#each sortPackagesByKey(packages, sortHeader, sortAscending) as pkg, idx (getPackageKey(pkg, idx))}
            <tr class:d-none={filterColumn(pkg)}>
                <td>{pkg.name}</td>
                <td>{pkg.version}</td>
                <td>
                    {pkg.date}
                </td>
                <td>
                    {pkg.build_id}
                </td>
                <td>{pkg.revision_id}</td>
            </tr>
        {:else}
            <tr>
                <td colspan="5"> No packages </td>
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
