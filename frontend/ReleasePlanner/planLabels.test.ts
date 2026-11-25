import { describe, expect, it } from "vitest";
import {
    addLabel,
    dropEntity,
    labelCounts,
    labelsOf,
    matchesLabels,
    optionsDiff,
    parseOptions,
    planLabelAvailable,
    planLabelMatches,
    planLabelOptions,
    planLabelsOfTest,
    removeLabel,
} from "./planLabels";

describe("plan labels", () => {
    it("parses the options string the API sends", () => {
        expect(parseOptions('{"t1": {"labels": ["week1"]}}')).toEqual({ t1: { labels: ["week1"] } });
        expect(parseOptions(null)).toEqual({});
        expect(parseOptions("not json")).toEqual({});
    });

    it("gives a test its own labels and its group's", () => {
        const options = { t1: { labels: ["week1"] }, g1: { labels: ["Week1", "sanity"] } };

        expect(labelsOf(options, "t1", "g1")).toEqual(["week1", "sanity"]);
        expect(labelsOf(options, "t2", "g1")).toEqual(["Week1", "sanity"]);
        expect(labelsOf(options, "t3")).toEqual([]);
    });

    it("refuses an empty label and a duplicate that differs in case", () => {
        const options = { t1: { labels: ["week1"] } };

        expect(addLabel(options, "t1", "  ")).toBe("A label cannot be empty");
        expect(addLabel(options, "t1", "WEEK1")).toBe("The label WEEK1 is already there");
        expect(addLabel(options, "t1", " sanity ")).toEqual({ t1: { labels: ["week1", "sanity"] } });
    });

    it("drops an entity whose last label goes", () => {
        const options = { t1: { labels: ["week1"] }, t2: { labels: ["a", "b"] } };

        expect(removeLabel(options, "t1", "week1")).toEqual({ t2: { labels: ["a", "b"] } });
        expect(removeLabel(options, "t2", "a")).toEqual({ t1: { labels: ["week1"] }, t2: { labels: ["b"] } });
        expect(dropEntity(options, "t2")).toEqual({ t1: { labels: ["week1"] } });
    });

    it("sends the changed entities and the emptied ones", () => {
        const original = { t1: { labels: ["week1"] }, t2: { labels: ["sanity"] }, t3: { labels: ["perf"] } };
        const current = { t1: { labels: ["week1"] }, t2: { labels: ["sanity", "week2"] }, t4: { labels: ["new"] } };

        expect(optionsDiff(original, current)).toEqual({
            options_set: { t2: { labels: ["sanity", "week2"] }, t4: { labels: ["new"] } },
            options_remove: ["t3"],
        });
    });

    it("counts each label, a group counting its tests", () => {
        const options = { t1: { labels: ["week1"] }, g1: { labels: ["week1", "sanity"] } };

        expect(labelCounts(options, (id) => (id === "g1" ? 4 : 1))).toEqual([
            { label: "sanity", count: 4 },
            { label: "week1", count: 5 },
        ]);
    });

    it("matches any selected label, ignoring case", () => {
        expect(matchesLabels(["Week1"], ["week1"])).toBe(true);
        expect(matchesLabels(["sanity"], ["week1"])).toBe(false);
        expect(matchesLabels([], [])).toBe(true);
    });

    it("offers one dashboard filter entry per plan and label", () => {
        const plans = [
            { id: "p1", name: "week plan", options: { t1: { labels: ["week1", "week2"] } } },
            { id: "p2", name: "rc plan", options: {} },
        ];

        expect(planLabelOptions(plans).map((option) => option.key)).toEqual(["p1:week1", "p1:week2"]);
    });

    it("keeps the tests that carry the selected plan label, directly or through their group", () => {
        const plans = [{ id: "p1", name: "week plan", options: { t1: { labels: ["week1"] }, g2: { labels: ["Week1"] } } }];
        const selection = { planId: "p1", label: "week1" };

        expect(planLabelMatches(plans, selection, "t1", "g1")).toBe(true);
        expect(planLabelMatches(plans, selection, "t5", "g2")).toBe(true);
        expect(planLabelMatches(plans, selection, "t3", "g3")).toBe(false);
        expect(planLabelMatches(plans, undefined, "t3", "g3")).toBe(true);
        expect(planLabelsOfTest(plans, selection, "t5", "g2")).toEqual(["Week1"]);
    });

    it("ignores a selection whose plan or label is gone, so a saved filter cannot hide every test", () => {
        const plans = [{ id: "p1", name: "week plan", options: { t1: { labels: ["week1"] } } }];

        for (const selection of [{ planId: "gone", label: "week1" }, { planId: "p1", label: "week2" }]) {
            expect(planLabelAvailable(plans, selection)).toBe(false);
            expect(planLabelMatches(plans, selection, "t3", "g3")).toBe(true);
            expect(planLabelsOfTest(plans, selection, "t1")).toEqual([]);
        }
        expect(planLabelMatches([], { planId: "p1", label: "week1" }, "t3", "g3")).toBe(true);
    });
});
