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
