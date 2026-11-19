import { describe, expect, it } from "vitest";
import { sanitizeHtml } from "./safeHtml";

const parse = (html: string): HTMLElement => {
    const holder = document.createElement("div");
    holder.innerHTML = html;
    return holder;
};

describe("sanitizeHtml", () => {
    it("strips script from server HTML", () => {
        const html = sanitizeHtml('<a href="javascript:alert(1)">x</a><img src="x" onerror="alert(1)"><script>alert(2)</script>');
        const node = parse(html);

        expect(node.querySelector("a")?.hasAttribute("href")).toBe(false);
        expect(node.querySelector("img")?.hasAttribute("onerror")).toBe(false);
        expect(node.querySelector("script")).toBeNull();
        expect(html).not.toContain("alert");
    });

    it("keeps the links and markup the server sends", () => {
        const regression = sanitizeHtml(
            "[admin] Setting run status to failed due to performance metric 'p99' falling below allowed threshold (-5): "
            + "-7% compared to <a href='/test/t1/runs?additionalRuns[]=r1&additionalRuns[]=r2'>This 2025.1 (#12) run</a>",
        );
        const mention = sanitizeHtml(
            "You were mentioned by <span class='fw-bold'>@admin</span> in a discussion of "
            + "<a href='/test/t1/runs?additionalRuns%5B%5D=r1'>job#7</a>.",
        );
        const pytestField = sanitizeHtml('<a href="https://jenkins.test/job/1">build log</a>');
        const description = sanitizeHtml('Scylla version.<br>See <a href="https://docs.test/x">the docs</a>.');

        expect(parse(regression).querySelector("a")?.getAttribute("href"))
            .toBe("/test/t1/runs?additionalRuns[]=r1&additionalRuns[]=r2");
        expect(parse(mention).querySelector("span.fw-bold")?.textContent).toBe("@admin");
        expect(parse(mention).querySelector("a")?.getAttribute("href")).toBe("/test/t1/runs?additionalRuns%5B%5D=r1");
        expect(parse(pytestField).querySelector("a")?.getAttribute("href")).toBe("https://jenkins.test/job/1");
        expect(parse(description).querySelector("br")).not.toBeNull();
        expect(parse(description).querySelector("a")?.getAttribute("href")).toBe("https://docs.test/x");
    });

    it("strips script from the validation message", () => {
        const branch = '"><img src=x onerror=alert(1)>';
        const html = sanitizeHtml(
            `Pipeline file not found in the <a href="https://github.com/scylladb/scylla-cluster-tests/tree/${branch}"> `
            + "target repository</a>, please check the repository before continuing",
        );
        const node = parse(html);

        expect(node.querySelector("a")?.getAttribute("href")).toBe("https://github.com/scylladb/scylla-cluster-tests/tree/");
        expect(node.querySelector("[onerror]")).toBeNull();
        expect(html).toContain("target repository");
    });

    it("keeps target on a link and forces rel", () => {
        const link = parse(sanitizeHtml('<a href="https://jenkins.test/job/1" target="_blank">log</a>')).querySelector("a");

        expect(link?.getAttribute("target")).toBe("_blank");
        expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
        expect(parse(sanitizeHtml('<a href="/x" target="_blank" rel="opener">x</a>')).querySelector("a")?.getAttribute("rel"))
            .toBe("noopener noreferrer");
    });

    it("keeps a target without href harmless", () => {
        const link = parse(sanitizeHtml('<a target="_blank" onclick="alert(1)">x</a>')).querySelector("a");

        expect(link?.hasAttribute("href")).toBe(false);
        expect(link?.hasAttribute("onclick")).toBe(false);
        expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
    });

    it("keeps the markup and the run link of a results graph tooltip", () => {
        const node = parse(sanitizeHtml(
            '<div class="custom-tooltip"><div class="tooltip-title">'
            + '<span style="display: inline-block; width: 10px; height: 10px; background-color: rgb(1, 2, 3);"></span>'
            + "2026-11-19: 12.00 (error threshold: N/A)</div>"
            + '<div class="tooltip-body">scylla: 2025.1.0 -&gt; 2025.1.1</div>'
            + '<div class="d-flex justify-content-end mt-2"><a href="/tests/scylla-cluster-tests/r1" class="btn btn-success btn-sm" '
            + 'target="_blank">Open <i class="fas fa-external-link-alt"></i></a></div><hr class="tooltip-separator"></div>',
        ));
        const open = node.querySelector("a");

        expect(node.querySelector(".custom-tooltip .tooltip-title span")?.getAttribute("style")).toContain("background-color");
        expect(node.querySelector(".tooltip-body")?.textContent).toBe("scylla: 2025.1.0 -> 2025.1.1");
        expect(open?.getAttribute("href")).toBe("/tests/scylla-cluster-tests/r1");
        expect(open?.getAttribute("class")).toBe("btn btn-success btn-sm");
        expect(open?.getAttribute("target")).toBe("_blank");
        expect(open?.querySelector("i.fas.fa-external-link-alt")).not.toBeNull();
        expect(node.querySelector("hr.tooltip-separator")).not.toBeNull();
    });

    it("returns an empty string for a missing value", () => {
        expect(sanitizeHtml(undefined)).toBe("");
        expect(sanitizeHtml(null)).toBe("");
    });
});
