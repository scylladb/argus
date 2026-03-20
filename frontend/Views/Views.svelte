<script module>
    export interface View {
        id: string,
        name: string,
        display_name: string,
        description: string,
        user_id: string,
        plan_id: string,
        tests: string[],
        release_ids: string[],
        group_ids: string[],
        created: string,
        last_updated: string,
        widget_settings: string,
    }

    type ViewProp = keyof View;

    type UserFavorites = string[];

    const loadUserPref = function<T>(key: string): T | null {
        let stored = window.localStorage.getItem(key);
        if (!stored) return null;
        try {
            let v = JSON.parse(stored);
            return v as T;
        } catch (e) {
            return null;
        }
    }

    const saveUserPref = function<T>(key: string, value: T) {
        const serializedValue = JSON.stringify(value);
        window.localStorage.setItem(key, serializedValue);
    }

    const FAVORITES_KEY = "viewsUserFavorites";
    const CURRENT_TAB_KEY = "viewsCurrentTab";

</script>

<script lang="ts">
    import Fa from "svelte-fa";
    import ViewRow from "./ViewRow.svelte";
    import { faPlus } from "@fortawesome/free-solid-svg-icons";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import ViewsManager from "../AdminPanel/ViewsManager.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import type { APIError } from "../TestRun/TestRun.svelte";


    interface Props {
        views: View[]
    }

    let { views }: Props = $props();

    enum Tab {
        Automatic,
        User,
        Favorite,
    }

    let userFavoriteStore = $state(loadUserPref<UserFavorites>(FAVORITES_KEY) || []);
    let currentTab = $state(loadUserPref<Tab>(CURRENT_TAB_KEY) ?? Tab.Automatic);
    let filterString = $state("");
    let creatingView = $state(false);
    let shouldHighlight: string | null = $state(null);

    const filterViews = function(views: View[], filter: (v: View) => boolean) {
        return views.filter(filter);
    }

    const isFavorite = function(view: View): boolean {
        return userFavoriteStore.includes(view.id);
    }

    const toggleFavorite = function(view: View) {
        if (isFavorite(view)) {
            userFavoriteStore = userFavoriteStore.filter(v => v != view.id);
        } else {
            userFavoriteStore.push(view.id);
        }
        saveUserPref(FAVORITES_KEY, userFavoriteStore);
    }

    const onTabChange = function(target: Tab) {
        currentTab = target;
        saveUserPref(CURRENT_TAB_KEY, currentTab);
    }

    const onViewCreate = async function(view: View) {
        creatingView = false;
        try {
            const response = await fetch("/api/v1/views/all");

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            views = json.response;
            shouldHighlight = view.id;
            setTimeout(() => {
                shouldHighlight = null;
            }, 5 * 1000);
            currentTab = Tab.User;
        } catch (e) {
            if ((e as APIError)?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching views.\nMessage: ${(e as APIError).response.arguments[0]}`,
                    "Views::onViewCreate"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view fetch",
                    "Views::onViewCreate"
                );
                console.log(e);
            }
        }
    }

    const sortViews = function(views: View[], key: ViewProp) {
        return [...views].sort((a, b) => {
            if (a[key] > b[key]) {
                return 1;
            } else if (a[key] == b[key]) {
                return 0;
            } else {
                return -1;
            }
        });
    }


</script>

{#if creatingView}
<ModalWindow on:modalClose={() => creatingView = false}>
    {#snippet title()}
            <div>Creating new View</div>
        {/snippet}
    {#snippet body()}
        <ViewsManager enableManager={false} createCallback={onViewCreate} />
    {/snippet}
</ModalWindow>
{/if}

<div class="container rounded shadow-sm bg-white my-2">
    <div class="p-2">
        <div class="d-flex align-items-center bg-light-one rounded-top">
            <div class="d-flex align-items-center btn-group p-1 w-75">
                <button class:active={currentTab == Tab.Automatic} class="btn btn-primary" onclick={() => onTabChange(Tab.Automatic)}>Automatic</button>
                <button class:active={currentTab == Tab.User} class="btn btn-primary" onclick={() => onTabChange(Tab.User)}>User-Generated</button>
                <button class:active={currentTab == Tab.Favorite} class="btn btn-primary" onclick={() => onTabChange(Tab.Favorite)}>Favorite</button>
            </div>
            <button class="ms-auto me-2 btn btn-success" onclick={() => creatingView = true}><Fa icon={faPlus}/> New View</button>
        </div>
        <div class="p-2 rounded-bottom bg-light-one">
            <div class="p-2 rounded bg-white mb-2">
                <input type="text" class="form-control" placeholder="Filter views..." bind:value={filterString}>
            </div>
            <div class:d-none={currentTab != Tab.Automatic}>
                {#each sortViews(filterViews(views, (v) => (v.description || "").toLowerCase().includes("automatic view")), "display_name") as view}
                    <ViewRow {shouldHighlight} {view} {toggleFavorite} {isFavorite} {filterString}/>
                {:else}
                    <div class="p-4 text-center text-muted">
                        No automatic views.
                    </div>
                {/each}
            </div>
            <div class:d-none={currentTab != Tab.User}>
                {#each sortViews(filterViews(views, (v) => !(v.description || "").toLowerCase().includes("automatic view")), "display_name") as view}
                    <ViewRow {shouldHighlight} {view} {toggleFavorite} {isFavorite} {filterString}/>
                {:else}
                    <div class="p-4 text-center text-muted">
                        No user-generated views.
                    </div>
                {/each}
            </div>
            <div class:d-none={currentTab != Tab.Favorite}>
                {#each sortViews(filterViews(views, (v) => isFavorite(v)), "display_name") as view}
                    <ViewRow {shouldHighlight} {view} {toggleFavorite} {isFavorite} {filterString}/>
                {:else}
                    <div class="p-4 text-center text-muted">
                        No favorite views.
                    </div>
                {/each}
            </div>
        </div>
    </div>
</div>
