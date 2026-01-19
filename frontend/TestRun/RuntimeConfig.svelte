<script lang="ts">
    import { faCopy, faLink } from "@fortawesome/free-solid-svg-icons";
    import queryString from "query-string";
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { quadIn } from "svelte/easing";

    let {
        name,
        content,
    }: {
        name: string,
        content: string,
    } = $props();

    let filterString = $state("");

    const checkFilter = function (key: string, value: string): boolean {
        if (!filterString) return false;
        try {
            return !(new RegExp(filterString, "i")).test(`${key}${value}`);
        } catch(e) {
            return false;
        }
    }

    const isScalar = function (value: string | number | any[] | Object | null | undefined) {
        if (!value) return true;
        switch (typeof value) {
            case "object":
            case "function": {
                return false;
            }
            case "string":
            case "number":
            case "bigint":
            case "boolean":
            case "undefined":
            case "symbol":
            default: {
                return true;
            }
        }
    };

    const isArrayLike = function (value: { length?: number }) {
        return !!(value.length);
    };

    const walkConfig = function(name: string, config: string) {
        const parsed = JSON.parse(config);
        if (typeof parsed === "object" && parsed.length) throw new Error("Top-level config object is not a mapping!");
        type Param = {
            name: string,
            value: any,
        };
        let entries = Array.from(Object.entries(parsed).map(([key, value]) => [`${name}`, key, value]));
        let params: Param[] = [];
        for (let [level, key, value] of entries) {
            if (isScalar(value as any)) {
                params.push({ name: `${level}${key}`, value: value });
            } else {
                if (isArrayLike(value as any)) {
                    entries.push(...(value as any[]).map((v, idx) => [`${level}${key}.`, idx.toString(), v]));
                } else {
                    entries.push(...Object.entries(value as object).map(([inner_key, value]) => [`${level}${key}.`, inner_key, value]));
                }
            }
        }
        params.sort((a: Param, b: Param) => a.name > b.name ? 1 : b.name > a.name ? -1 : 0);
        return params;
    }


    onMount(() => {
        const hs = queryString.parse(document.location.hash.slice(1));
        if (hs.configKey) filterString = hs.configKey as string;
    })
</script>

<div class="mb-2">
    <h4>{name}</h4>
    <div class="mb-1">
        <input type="text" class="form-control w-100" bind:value={filterString} placeholder="Filter configuration...">
    </div>
    <div class="overflow-x-clip rounded" style="max-height: 768px; overflow-y: scroll">
        <table class="table table-responsive table-striped table-bordered table-hover">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
                {#each walkConfig("", content) as param}
                    <tr class:d-none={checkFilter(param.name, JSON.stringify(param.value))} style="vertical-align: center;">
                        <td class="fw-bold">{param.name}</td>
                        <td>
                            <div class="input-group">
                                <input class="form-control" type="text" disabled value={param.value}>
                                <button class="d-none btn btn-primary" onclick={() => {
                                    let newHash = `configKey=${param.name}`;
                                    let oldUrl = document.location.href;
                                    let target = "";
                                    if (oldUrl.includes("#")) {
                                        target = oldUrl.replace(/#.+/, `#${newHash}`);
                                    } else {
                                        target = `${oldUrl}#${newHash}`;
                                    }
                                    navigator.clipboard.writeText(target);
                                }}><Fa icon={faLink}/></button>
                                <button class="d-none btn btn-success" onclick={() => navigator.clipboard.writeText(`${param.name}: ${param.value}`)}><Fa icon={faCopy}/></button>
                            </div>
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
</div>

<style>
    .input-group:hover button {
        display: inline !important;
    }
</style>
