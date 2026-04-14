import { describe, it, expect } from "vitest";
import {
    getScyllaPackage,
    getOperatorPackage,
    getOperatorHelmPackage,
    getOperatorHelmRepoPackage,
    getKernelPackage,
    getUpgradedScyllaPackage,
    getRelocatableScyllaPackage,
    extractBuildNumber,
    filterInvestigated,
    filterNotInvestigated,
    createScreenshotUrl,
} from "./RunUtils.js";

const samplePackages = [
    { name: "scylla-server", version: "5.2.0" },
    { name: "operator-image", version: "1.0.0" },
    { name: "operator-chart", version: "2.0.0" },
    { name: "operator-helm-repo", version: "3.0.0" },
    { name: "kernel", version: "5.15" },
    { name: "scylla-server-upgraded", version: "5.3.0" },
    { name: "relocatable_pkg", version: "1.0.0" },
];

describe("package finders", () => {
    it("getScyllaPackage finds scylla-server", () => {
        expect(getScyllaPackage(samplePackages)).toEqual({ name: "scylla-server", version: "5.2.0" });
    });

    it("getOperatorPackage finds operator-image", () => {
        expect(getOperatorPackage(samplePackages)).toEqual({ name: "operator-image", version: "1.0.0" });
    });

    it("getOperatorHelmPackage finds operator-chart", () => {
        expect(getOperatorHelmPackage(samplePackages)).toEqual({ name: "operator-chart", version: "2.0.0" });
    });

    it("getOperatorHelmRepoPackage finds operator-helm-repo", () => {
        expect(getOperatorHelmRepoPackage(samplePackages)).toEqual({ name: "operator-helm-repo", version: "3.0.0" });
    });

    it("getKernelPackage finds kernel", () => {
        expect(getKernelPackage(samplePackages)).toEqual({ name: "kernel", version: "5.15" });
    });

    it("getUpgradedScyllaPackage finds scylla-server-upgraded", () => {
        expect(getUpgradedScyllaPackage(samplePackages)).toEqual({ name: "scylla-server-upgraded", version: "5.3.0" });
    });

    it("getRelocatableScyllaPackage finds relocatable_pkg", () => {
        expect(getRelocatableScyllaPackage(samplePackages)).toEqual({ name: "relocatable_pkg", version: "1.0.0" });
    });

    it("returns undefined when package is not in the list", () => {
        expect(getScyllaPackage([])).toBeUndefined();
        expect(getOperatorPackage([{ name: "other", version: "1.0" }])).toBeUndefined();
    });
});

describe("extractBuildNumber", () => {
    it("extracts the build number from a Jenkins-style URL", () => {
        const run = { build_job_url: "https://jenkins.example.com/job/test/42/" };
        expect(extractBuildNumber(run)).toBe("42");
    });

    it("handles URLs with trailing whitespace", () => {
        const run = { build_job_url: "https://jenkins.example.com/job/test/99/  " };
        expect(extractBuildNumber(run)).toBe("99");
    });

    it("returns -1 when build_job_url is falsy", () => {
        expect(extractBuildNumber({ build_job_url: "" })).toBe(-1);
        expect(extractBuildNumber({ build_job_url: null })).toBe(-1);
        expect(extractBuildNumber({ build_job_url: undefined })).toBe(-1);
        expect(extractBuildNumber({})).toBe(-1);
    });
});

describe("filterInvestigated", () => {
    const jobs = [
        { investigation_status: "investigated", status: "failed", start_time: "2024-03-15T10:00:00Z" },
        { investigation_status: "not_investigated", status: "passed", start_time: "2024-03-16T10:00:00Z" },
        { investigation_status: "not_investigated", status: "failed", start_time: "2024-03-17T10:00:00Z" },
        { investigation_status: "investigated", status: "passed", start_time: "2024-03-14T10:00:00Z" },
    ];

    it("includes jobs that are investigated OR passed", () => {
        const result = filterInvestigated(jobs);
        // Jobs 0 (investigated), 1 (passed), 3 (both)
        expect(result).toHaveLength(3);
    });

    it("excludes jobs that are not investigated AND not passed", () => {
        const result = filterInvestigated(jobs);
        const hasUninvestigatedFailed = result.some(
            (j) => j.investigation_status === "not_investigated" && j.status === "failed",
        );
        expect(hasUninvestigatedFailed).toBe(false);
    });

    it("sorts by start_time descending (newest first)", () => {
        const result = filterInvestigated(jobs);
        for (let i = 1; i < result.length; i++) {
            expect(new Date(result[i - 1].start_time).getTime()).toBeGreaterThanOrEqual(
                new Date(result[i].start_time).getTime(),
            );
        }
    });

    it("returns empty array for empty input", () => {
        expect(filterInvestigated([])).toEqual([]);
    });
});

describe("filterNotInvestigated", () => {
    const jobs = [
        { investigation_status: "investigated", status: "failed", start_time: "2024-03-15T10:00:00Z" },
        { investigation_status: "not_investigated", status: "passed", start_time: "2024-03-16T10:00:00Z" },
        { investigation_status: "not_investigated", status: "failed", start_time: "2024-03-17T10:00:00Z" },
    ];

    it("includes jobs that are NOT investigated AND NOT passed", () => {
        const result = filterNotInvestigated(jobs);
        expect(result).toHaveLength(1);
        expect(result[0].start_time).toBe("2024-03-17T10:00:00Z");
    });

    it("sorts by start_time descending", () => {
        const moreJobs = [
            { investigation_status: "not_investigated", status: "failed", start_time: "2024-03-10T10:00:00Z" },
            { investigation_status: "not_investigated", status: "error", start_time: "2024-03-20T10:00:00Z" },
        ];
        const result = filterNotInvestigated(moreJobs);
        expect(new Date(result[0].start_time).getTime()).toBeGreaterThan(new Date(result[1].start_time).getTime());
    });

    it("returns empty array when all jobs are investigated or passed", () => {
        const allGood = [
            { investigation_status: "investigated", status: "failed", start_time: "2024-01-01T00:00:00Z" },
            { investigation_status: "not_investigated", status: "passed", start_time: "2024-01-02T00:00:00Z" },
        ];
        expect(filterNotInvestigated(allGood)).toEqual([]);
    });
});

describe("createScreenshotUrl", () => {
    it("builds the correct proxy URL", () => {
        const url = createScreenshotUrl(
            "scylla-cluster-tests",
            "abc-123",
            "https://s3.amazonaws.com/bucket/screenshots/shot1.png",
        );
        expect(url).toBe("/api/v1/tests/scylla-cluster-tests/abc-123/screenshot/shot1.png");
    });

    it("extracts filename from the end of the link path", () => {
        const url = createScreenshotUrl("generic", "id-1", "https://cdn.example.com/a/b/c/image.jpg");
        expect(url).toBe("/api/v1/tests/generic/id-1/screenshot/image.jpg");
    });
});
