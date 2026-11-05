export const getScyllaPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "scylla-server");
};

export const getOperatorPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "operator-image");
};

export const getOperatorHelmPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "operator-chart");
};

export const getOperatorHelmRepoPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "operator-helm-repo");
};

export const getKernelPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "kernel");
};

export const getUpgradedScyllaPackage = function(packages) {
    return packages.find((pkg) => pkg.name == "scylla-server-upgraded");
};

export const extractBuildNumber = function (run) {
    return run.build_job_url ? run.build_job_url.trim().split("/").reverse()[1] : -1;
};

const SCT_REGION_ENV_VAR_MAP = {
    aws: "SCT_REGION_NAME",
    "aws-siren": "SCT_REGION_NAME",
    "k8s-eks": "SCT_REGION_NAME",
    gce: "SCT_GCE_DATACENTER",
    "gce-siren": "SCT_GCE_DATACENTER",
    "k8s-gke": "SCT_GCE_DATACENTER",
    azure: "SCT_AZURE_REGION_NAME",
    oci: "SCT_OCI_REGION_NAME",
};

/**
 * Build the copyable "hydra clean-resources" command for a run, prefixed with
 * the backend-specific region env var when a known region is available.
 * @param {string} backend
 * @param {string[]} regions
 * @param {string} runId
 * @returns {string}
 */
export const buildCleanResourcesCommand = function (backend, regions, runId) {
    const envVar = SCT_REGION_ENV_VAR_MAP[backend];
    const hasKnownRegions = regions && regions.length > 0 && regions.some((region) => region != "undefined_region");
    if (envVar && hasKnownRegions) {
        return `${envVar}="${regions.join(" ")}" hydra clean-resources --backend ${backend} --test-id ${runId}`;
    }
    return `hydra clean-resources --backend ${backend} --test-id ${runId}`;
};

/**
 * Older runs report no resource_type, so the monitor name is the fallback.
 * @returns {boolean}
 */
export const isMonitorResource = function (resource) {
    return resource.resource_type === "monitor" || /-monitor-node-/.test(resource.name);
};

// hydra runs sct.py in docker; uv runs it from an SCT checkout without docker.
const SCT_RUNNERS = ["hydra", "uv run sct.py"];

/**
 * The SCT commands that reach the monitor of a run: a tunnel while the
 * monitor node is up (it has no public IP), and the restored monitor once
 * the run is done and its logs are collected.
 * @param {string} testId
 * @param {{ name: string } | undefined} runningMonitor
 * @param {boolean} runFinished
 * @returns {{ label: string, commands: string[] }[]}
 */
export const buildMonitorCommands = function (testId, runningMonitor, runFinished) {
    const entries = [];
    if (runningMonitor) {
        entries.push(["Grafana", `tunnel -t ${testId} -p 3000 ${runningMonitor.name}`]);
        entries.push(["Prometheus", `tunnel -t ${testId} -p 9090 ${runningMonitor.name}`]);
    }
    if (runFinished) {
        entries.push(["Restore monitor", `investigate show-monitor ${testId}`]);
    }
    return entries.map(([label, args]) => ({ label, commands: SCT_RUNNERS.map((runner) => `${runner} ${args}`) }));
};

export const getRelocatableScyllaPackage = function(packages) {
    // relocatable package: https://docs.scylladb.com/stable/getting-started/install-scylla/unified-installer.html
    return packages.find((pkg) => pkg.name == "relocatable_pkg");
};

export const filterInvestigated = function (jobs) {
    return jobs.filter(
        (job) =>
            job.investigation_status == "investigated" ||
            job.status == "passed"
    ).sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
};

export const filterNotInvestigated = function (jobs) {
    return jobs.filter(
        (job) =>
            job.investigation_status != "investigated" &&
            job.status != "passed"
    ).sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
};

/**
 * @param {string} runType
 * @param {string} runId
 */
export const fetchRun = async function(runType, runId) {
    let res = await fetch(`/api/v1/run/${runType}/${runId}`);
    if (res.status != 200) {
        return Promise.reject(`HTTP Error ${res.status} trying to fetch a test run`);
    }
    let run = await res.json();
    if (run.status != "ok") {
        return Promise.reject(`API Error: ${run.message}, while trying to fetch a test run`);
    }

    return run.response;
};


/**
 * Create argus proxy link for the image stored on s3
 * @param {string} link
 * @returns
 */
export const createScreenshotUrl = function (plugin, id, link) {
    const name = link.split("/").reverse()[0];
    return `/api/v1/tests/${plugin}/${id}/screenshot/${name}`;
};
