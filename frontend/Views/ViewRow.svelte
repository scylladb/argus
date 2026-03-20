<script lang="ts">
    import Fa from "svelte-fa";
    import { timestampToISODate } from "../Common/DateUtils";
    import { getUser } from "../Common/UserUtils";
    import User from "../Profile/User.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import type { View } from "./Views.svelte";
    import { faDashboard, faHeart } from "@fortawesome/free-solid-svg-icons";
    import { faHeart as faHeartEmpty } from "@fortawesome/free-regular-svg-icons";
    import { onDestroy } from "svelte";


    interface Props {
        view: View,
        toggleFavorite: (view: View) => void,
        isFavorite: (view: View) => boolean,
        filterString: string,
        shouldHighlight: string | null,
    }

    let users = $state({});
    let domNode: Element | null = $state(null);

    let unsub = userList.subscribe((value) => {
        users = value;
    });

    let { view, filterString, toggleFavorite, isFavorite, shouldHighlight }: Props = $props();

    const shouldHide = function(): boolean {
        const term = `${view.display_name}${view.name}${view.description}`;
        return filterString ? !term.toLowerCase().includes(filterString.toLowerCase()) : false;
    }

    $effect(() => {
        if (shouldHighlight == view.id) {
            domNode?.scrollIntoView({
                behavior: "smooth",
                block: "center",
            })
        }
    });


    onDestroy(() => {
        unsub();
    })


</script>

<div bind:this={domNode}  class:highlight={shouldHighlight == view.id} class:d-none={shouldHide()}>
    <div class="mb-2 rounded bg-white shadow-sm overflow-hidden">
        <div class="border-bottom px-2 py-1 fs-4 d-flex align-items-center" style="background-color: #f0f0f0;">
            <div>{view.display_name || view.name}</div>
            <button class="ms-auto btn btn-danger" onclick={() => toggleFavorite(view)}><Fa icon={isFavorite(view) ? faHeart : faHeartEmpty} /></button>
            <div class="ms-2"><a href="/view/{view.name}" class="btn btn-primary"><Fa icon={faDashboard}/> View Dashboard</a></div>
        </div>
        <div class="p-2 d-flex align-items-center">
            <div class="rounded bg-light-three p-1 w-75">{view.description || "No description provided"}</div>
            <div class="p-2 d-flex align-items-center justify-content-end flex-fill" style="font-size: 0.8em">
                <div>
                    Created at <span class="fw-bold">{timestampToISODate(view.created)}</span> by
                </div>
                <div class="ms-1">
                    <User item={getUser(view.user_id, users)}/>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    @keyframes highlight-pulse {
        0%, 100% { box-shadow: 0 0 0 0 #2d98c200; }
        50%       { box-shadow: 0 0 0 7px #222a2ea6; }
    }

    .highlight {
        animation: highlight-pulse 1.55s ease-in-out 6;
    }
</style>
