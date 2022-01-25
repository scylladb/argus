<script>
    export let resources;
    export let id;
    export let caption = "";
    import { timestampToISODate } from "../Common/DateUtils";
    let shortCaption = caption.replaceAll(" ", "");

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };
</script>

<div class="accordion-item">
    <h5 class="accordion-header" id="header{shortCaption}-{id}">
        <button
            class="accordion-button collapsed"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{shortCaption}-{id}">{caption}</button
        >
    </h5>
    <div
        id="collapse{shortCaption}-{id}"
        class="accordion-collapse collapse"
        data-bs-parent="#accordionResources-{id}"
    >
        <div class="accordion-body">
            <div class="container-fluid p-0 m-0">
                <div class="row align-items-center p-1 m-0">
                    {#each resources as resource, idx}
                        <div class="col-4 mb-1 p-1">
                            <div class="card">
                                <div class="card-body">
                                    <h6 class="card-title">
                                        {resource.name}
                                    </h6>
                                    <div class="card-text">
                                        <div>
                                            Status: {titleCase(resource.state)}
                                        </div>
                                        <ul>
                                            <li>
                                                Public IP: {resource
                                                    .instance_info.public_ip}
                                            </li>
                                            <li>
                                                Private IP: {resource
                                                    .instance_info.private_ip}
                                            </li>
                                            <li>
                                                Provider: {resource
                                                    .instance_info.provider}
                                            </li>
                                            <li>
                                                Region: {resource.instance_info
                                                    .region}
                                            </li>
                                            {#if resource.instance_info.shards_amount > 0}
                                            <li>
                                                Shards: {resource.instance_info
                                                    .shards_amount}
                                            </li>
                                            {/if}
                                            <li>
                                                Created at {timestampToISODate(
                                                    resource.instance_info
                                                        .creation_time * 1000,
                                                    true
                                                )}
                                            </li>
                                            {#if resource.instance_info.termination_time != 0}
                                                <li>
                                                    Terminated at {timestampToISODate(
                                                        resource.instance_info
                                                            .termination_time *
                                                            1000,
                                                        true
                                                    )}
                                                </li>
                                                <li>
                                                    Termination reason: {resource.instance_info.termination_reason.split(
                                                        " "
                                                    )[0]}
                                                </li>
                                            {/if}
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    {/each}
                </div>
            </div>
        </div>
    </div>
</div>
