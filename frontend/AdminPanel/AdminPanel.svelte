<script>
    import { onMount } from "svelte";
    import { titleCase } from "../Common/TextUtils";
    import AdminPanelWelcome from "./AdminPanelWelcome.svelte";
    import UserManager from "./UserManager.svelte";
    import ReleaseManager from "./ReleaseManager.svelte";
    import ViewsManager from "./ViewsManager.svelte";

    let { currentRoute = $bindable() } = $props();

    const routes = {
        index: AdminPanelWelcome,
        users: UserManager,
        releases: ReleaseManager,
        views: ViewsManager,
    };

    const handleRouteClick = function(route, event) {
        history.pushState({}, "", `/admin/${route}`);
        let prevRoute = currentRoute;
        currentRoute = route;
        document.title = document.title.replace(titleCase(prevRoute), titleCase(route));
    };

    onMount(() => {
        document.title = document.title.replace("%ROUTE", titleCase(currentRoute));
    });

    const SvelteComponent = $derived(routes[currentRoute] ?? routes["index"]);
</script>

<div class="container-fluid">
    <div class="row">
        <div class="col-2 min-vh-100 border-end p-0 bg-light-two">
            <ul class="list-group list-group-flush">
                <li class="list-group-item">
                    <button
                        class:btn-primary={currentRoute == "index"}
                        class:btn-outline-primary={currentRoute != "index"}
                        class="btn h-100 w-100"
                        onclick={(e) => handleRouteClick("index", e)}
                    >
                        Home
                    </button>
                </li>
                <li class="list-group-item">
                    <button
                        class:btn-primary={currentRoute == "users"}
                        class:btn-outline-primary={currentRoute != "users"}
                        class="btn h-100 w-100"
                        onclick={(e) => handleRouteClick("users", e)}
                    >
                        Users
                    </button>
                </li>
                <li class="list-group-item">
                    <button
                        class:btn-primary={currentRoute == "releases"}
                        class:btn-outline-primary={currentRoute != "releases"}
                        class="btn h-100 w-100"
                        onclick={(e) => handleRouteClick("releases", e)}
                    >
                        Releases
                    </button>
                </li>
                <li class="list-group-item">
                    <button
                        class:btn-primary={currentRoute == "views"}
                        class:btn-outline-primary={currentRoute != "views"}
                        class="btn h-100 w-100"
                        onclick={(e) => handleRouteClick("views", e)}
                    >
                        Views
                    </button>
                </li>
            </ul>
        </div>
        <div class="col-9 min-vh-100 ">
            <SvelteComponent />
        </div>
    </div>
</div>
