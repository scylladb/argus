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
    return run.build_job_url.trim().split("/").reverse()[1];
};

export const getRelocatableScyllaPackage = function(packages) {
    // relocatable package: https://docs.scylladb.com/stable/getting-started/install-scylla/unified-installer.html
    return packages.find((pkg) => pkg.name == "relocatable_pkg");
};
