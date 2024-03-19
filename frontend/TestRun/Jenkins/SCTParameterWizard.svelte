<script>
    import Fa from "svelte-fa";
    import { sanitizeSelector } from "../../Common/TextUtils";
    import { Collapse } from "bootstrap";
    import DummySelectParam from "./DummySelectParam.svelte";
    import SelectParam from "./SelectParam.svelte";
    import StringParam from "./StringParam.svelte";
    import { faExclamationCircle, faMinus, faPlus, faQuestionCircle } from "@fortawesome/free-solid-svg-icons";

    /**@type {{[string]: string}}*/
    export let params = {};
    export let rawParams = [];

    const determineVersionSource = function(params) {
        const keysToCheck = {
            scylla_version: "scylla_version",
            scylla_repo: "scylla_repo",
            new_scylla_repo: "rolling_upgrade",
            scylla_ami_id: "scylla_image",
            gce_image_db: "scylla_image",
            azure_image_db: "scylla_image",
        };

        for (const [key, type] of Object.entries(keysToCheck)) {
            if (params[key]) {
                return type;
            }
        }
        return keysToCheck.scylla_version;
    };

    const conditionWrapper = function(definition, params, allDefs) {
        if (!(definition.internalName in params) && !definition.formOnly) return false;
        const result = definition.condition(params, allDefs);
        if (result && definition.onShow) {
            definition.onShow(params);
        } else if (!result && definition.onHide) {
            definition.onHide(params);
        }
        return result;
    };

    const ALL_BACKENDS = {
        azure: "Microsoft Azure",
        aws: "Amazon AWS", 
        "aws-siren": "Amazon AWS (Siren-tests)", 
        "k8s-local-kind-aws": "Kubernetes in Docker on AWS", 
        "k8s-eks": "Kubernetes (Amazon EKS)",
        gce: "Google Cloud",
        "gce-siren": "Google Cloud (Siren-tests)",
        "k8s-local-kind-gce": "Kubernetes in Docker on GCE", 
        "k8s-gke": "Kubernetes (Google Kubernetes Engine)",
    };

    /**
     * 
     * @param {string} backend
     * @param {string} group
     */
    const inBackendGroup = function (backend, group) {
        const BACKEND_GROUPS = {
            aws: ["aws", "aws-siren", "k8s-local-kind-aws", "k8s-eks"],
            azure: ["azure"],
            gce: ["gce", "gce-siren", "k8s-local-kind-gce", "k8s-gke"],
            k8s: ["k8s-local-kind-aws", "k8s-eks", "k8s-gke"],
        };
        return (BACKEND_GROUPS[group] ?? []).includes(backend);
    };

    const paramDefinitions = {
        environment: {
            name: "Environment",
            params: {
                backend: {
                    name: "Cloud Backend",
                    description: "Cloud backend to use.",
                    type: SelectParam,
                    internalName: "backend",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    },
                    values: Object.keys(ALL_BACKENDS),
                    labels: Object.entries(ALL_BACKENDS).map(([k, v]) => `${v} (${k})`),
                },
                awsRegion: {
                    name: "Cloud Region",
                    description: "Only supported regions are displayed",
                    type: SelectParam,
                    internalName: "region",
                    condition: (params, defs) => inBackendGroup(params.backend, "aws"),
                    onShow: function (params) {
                        if (!params[this.internalName]) {
                            params[this.internalName] = this.values[0];
                        }
                    },
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["eu-west-1", "eu-west-2", "us-west-2", "us-east-1", "eu-north-1", "eu-central-1"],
                },
                azureRegion: {
                    name: "Cloud Region",
                    description: "Only supported regions are displayed",
                    type: SelectParam,
                    internalName: "azure_region_name",
                    condition: (params, defs) => inBackendGroup(params.backend, "azure"),
                    onShow: function (params) {
                        if (!params[this.internalName]) {
                            params[this.internalName] = this.values[0];
                        }
                    },
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["eastus"],
                },
                gceRegion: {
                    name: "Cloud Region",
                    description: "Only supported regions are displayed",
                    type: SelectParam,
                    internalName: "gce_datacenter",
                    condition: (params, defs) => inBackendGroup(params.backend, "gce"),
                    onShow: function (params) {
                        if (!params[this.internalName]) {
                            params[this.internalName] = this.values[0];
                        }
                    },
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["us-east1", "us-east4", "us-west1", "us-central1"],
                },
                availabilityZone: {
                    name: "Availability Zone",
                    description: "Availability zone for the region. Note that GCE only supports zones from a to d (with some exceptions)",
                    type: StringParam,
                    internalName: "availability_zone",
                    condition: (params, defs) => (true),
                    onChange: function (e, params) {
                        //empty
                    },
                },
                provisionType: {
                    name: "Provision Type",
                    type: SelectParam,
                    internalName: "provision_type",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["spot", "on_demand", "spot_fleet"],
                    labels: ["Spot", "On Demand", "Spot Fleet"]
                },
            }
        },
        scyllaVersion: {
            name: "Scylla Installation",
            show: true,
            currentSource: determineVersionSource(params),
            params: {
                masterSelect: {
                    name: "",
                    type: DummySelectParam,
                    formOnly: true,
                    args: {
                        value: determineVersionSource(params),
                    },
                    internalName: undefined,
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        paramDefinitions.scyllaVersion.currentSource = e.target.value;
                    },
                    values: ["scylla_version", "scylla_repo", "scylla_image", "rolling_upgrade"],
                    labels: ["Provide Scylla version directly", "Provide Scylla repo", "Specify Cloud Image", "Specify Rolling Upgrade Params"],
                },
                scyllaVersion: {
                    name: "Scylla Version",
                    description: "Short scylla version string, e.g. 5.2.9~rc0 or master:latest",
                    type: StringParam,
                    internalName: "scylla_version",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "scylla_version"),
                    onChange: function (e, params) {
                        params.scylla_repo = "";
                        params.scylla_ami_id = "";
                        params.gce_image_db = "";
                        params.azure_image_db = "";
                    }
                },
                scyllaRepo: {
                    name: "Scylla Repository",
                    description: "HTTP(s) link to the .repo/.list file",
                    type: StringParam,
                    internalName: "scylla_repo",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "scylla_repo"),
                    onChange: function (e, params) {
                        params.scylla_version = "";
                        params.scylla_ami_id = "";
                        params.gce_image_db = "";
                        params.azure_image_db = "";
                        this.validated = this.validate(params);
                    }
                },
                scyllaImageAWS: {
                    name: "Scylla AMI",
                    description: "AWS Machine Image id",
                    type: StringParam,
                    internalName: "scylla_ami_id",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "scylla_image" && inBackendGroup(params.backend, "aws")),
                    onChange: function (e, params) {
                        params.scylla_version = "";
                        params.scylla_repo = "";
                    }
                },
                scyllaImageGCE: {
                    name: "Scylla GCE Image",
                    description: "GCE ImageId",
                    type: StringParam,
                    internalName: "gce_image_db",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "scylla_image" && inBackendGroup(params.backend, "gce")),
                    onChange: function (e, params) {
                        params.scylla_version = "";
                        params.scylla_repo = "";
                    }
                },
                scyllaImageAzure: {
                    name: "Scylla Azure ImageId",
                    description: "Azure ImageId URI",
                    type: StringParam,
                    internalName: "azure_image_db",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "scylla_image" && inBackendGroup(params.backend, "azure")),
                    onChange: function (e, params) {
                        params.scylla_version = "";
                        params.scylla_repo = "";
                    }
                },
                updateDbPackages: {
                    name: "S3 or Google Storage URL for private packages",
                    description: "An s3:// or gs:// url is required to update scylla to specific packages",
                    type: StringParam,
                    internalName: "update_db_packages",
                    condition: (params, defs) => (true),
                    onChange: function (e, params) {
                        //empty
                    }
                },
                newScyllaRepo: {
                    name: "Repository to pull newest scylla version from",
                    type: StringParam,
                    internalName: "new_scylla_repo",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "rolling_upgrade"),
                    onChange: function (e, params) {
                        //empty
                    }
                },
                baseVersions: {
                    name: "Base Versions to upgrade from",
                    type: StringParam,
                    internalName: "base_versions",
                    condition: (params, defs) => (defs.scyllaVersion.currentSource == "rolling_upgrade"),
                    onChange: function (e, params) {
                        //empty
                    }
                },
            }
        },
        testConfiguration: {
            name: "Test configuration",
            params: {
                testName: {
                    name: "Test Name",
                    type: StringParam,
                    internalName: "test_name",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    }
                },
                testConfig: {
                    name: "Configuration to use",
                    type: StringParam,
                    internalName: "test_config",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    }
                },
                stressDuration: {
                    name: "Custom Stress Command Duration",
                    type: StringParam,
                    internalName: "stress_duration",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    }
                },

            }
        },
        clusterPostTestBehaviour: {
            name: "Cluster Post-Test Behaviour",
            params: {
                dbNodes: {
                    name: "Action for DB Cluster",
                    type: SelectParam,
                    internalName: "post_behavior_db_nodes",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["keep", "keep-on-failure", "destroy"],
                    labels: ["Keep", "Keep on Failure", "Destroy"],
                },
                loaderNodes: {
                    name: "Action for Loader nodes",
                    type: SelectParam,
                    internalName: "post_behavior_loader_nodes",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["keep", "keep-on-failure", "destroy"],
                    labels: ["Keep", "Keep on Failure", "Destroy"],
                },
                monitorNodes: {
                    name: "Action for Monitor nodes",
                    type: SelectParam,
                    internalName: "post_behavior_monitor_nodes",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["keep", "keep-on-failure", "destroy"],
                    labels: ["Keep", "Keep on Failure", "Destroy"],
                },
                k8sCluster: {
                    name: "Action for Kubernetes Cluster",
                    type: SelectParam,
                    internalName: "post_behavior_k8s_cluster",
                    condition: (params, defs) => inBackendGroup(params.backend, "k8s"),
                    onChange: function (e, params) {
                        //empty
                    },
                    values: ["keep", "keep-on-failure", "destroy"],
                    labels: ["Keep", "Keep on Failure", "Destroy"],
                }
            }
        },
        reportSettings: {
            name: "Reporting",
            show: true,
            params: {
                email_recipients: {
                    name: "Email Report Recepients",
                    description: "Comma separated list of email recipients",
                    type: StringParam,
                    internalName: "email_recipients",
                    condition: (params, defs) => true,
                    onChange: function (e, params) {
                        //empty
                    }
                },
            }
        }
    };
</script>


<div class="bg-light-three rounded p-2">
    {#each Object.entries(paramDefinitions) as [paramCategoryName, paramDef] (paramCategoryName)}
        <div class="rounded bg-white shadow-sm p-2 mb-2">
            <div class="fw-bold d-flex align-items-center">
                <div class="ms-2">
                    {paramDef.name}
                </div>
                <button 
                    class="ms-auto btn btn-outline-dark" 
                    type="button"
                    on:click={() => {
                        paramDef.show = !paramDef.show;
                        new Collapse(`#collapse-${paramCategoryName}`).toggle();
                    }}
                >
                    {#if paramDef.show}
                        <Fa icon={faMinus}/>
                    {:else}
                        <Fa icon={faPlus}/>
                    {/if}
                </button>
            </div>
            <div class="mt-2 collapse" class:show={paramDef.show} id="collapse-{paramCategoryName}">
                {#each Object.values(paramDef.params) as param (param.internalName)}
                    {#if conditionWrapper(param, params, paramDefinitions)}
                        <div class="my-2 text-sm">
                            <div class="form-label text-sm">
                                {param.name}
                                {#if param.internalName}
                                    <span class="display-6 text-sm text-muted" title={param.internalName}>
                                        <Fa icon={faQuestionCircle}/>
                                    </span>
                                {/if}
                            </div>
                            <svelte:component this={param.type} bind:definition={param} bind:params={params}/>
                            <div id="paramHelp{sanitizeSelector(param.internalName ?? "")}" class="form-text">{@html param.description ?? rawParams.find(v => v.name == param.internalName)?.description ?? ""}</div>
                            {#if !param.validated && param.requiresValidation}
                                <div class="alert alert-danger">
                                    <Fa icon={faExclamationCircle}/> {param.validationHelpText}
                                </div>
                            {/if}
                        </div>
                    {/if}
                {/each}
            </div>
        </div>
    {/each}
</div>

<style>
    .text-sm {
        font-size: 0.95em;
    }
</style>