<script>
    import { onMount } from "svelte";
    import AdminPanelWelcome from "./AdminPanelWelcome.svelte";
    import UserManager from "./UserManager.svelte";
    import ReleaseManager from "./ReleaseManager.svelte";
    import ViewsManager from "./ViewsManager.svelte";
    import ProxyTunnelManager from "./ProxyTunnelManager.svelte";

    let { currentRoute = $bindable() } = $props();

    const routes = {
        index: { component: AdminPanelWelcome, title: "Home" },
        users: { component: UserManager, title: "Users" },
        releases: { component: ReleaseManager, title: "Releases" },
        views: { component: ViewsManager, title: "Views" },
        "ssh-tunnel": { component: ProxyTunnelManager, title: "SSH Tunnel" },
    };

    const routeTitle = (route) => routes[route]?.title ?? route;

    const handleRouteClick = function (route, event) {
        history.pushState({}, "", `/admin/${route}`);
        let prevRoute = currentRoute;
        currentRoute = route;
        document.title = document.title.replace(routeTitle(prevRoute), routeTitle(route));
    };

    onMount(() => {
        document.title = document.title.replace("%ROUTE", routeTitle(currentRoute));
    });

    const SvelteComponent = $derived(routes[currentRoute]?.component ?? routes["index"].component);
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
                <li class="list-group-item">
                    <button
                        class:btn-primary={currentRoute == "ssh-tunnel"}
                        class:btn-outline-primary={currentRoute != "ssh-tunnel"}
                        class="btn h-100 w-100"
                        onclick={(e) => handleRouteClick("ssh-tunnel", e)}
                    >
                        SSH Tunnel
                    </button>
                </li>
            </ul>
        </div>
        <div class="col-9 min-vh-100">
            <SvelteComponent enableManager={true} />
        </div>
    </div>
</div>
