export const getScyllaPackage = function (packages) {
    return packages.find((pkg) => pkg.name == "scylla-server");
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

export const getRelocatableScyllaPackage = function(packages) {
    // relocatable package: https://docs.scylladb.com/stable/getting-started/install-scylla/unified-installer.html
    return packages.find((pkg) => pkg.name == "relocatable_pkg");
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
