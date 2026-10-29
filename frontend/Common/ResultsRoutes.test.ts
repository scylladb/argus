import { describe, it, expect } from "vitest";
import { ResultsRoutes } from "./ResultsRoutes";

describe("ResultsRoutes", () => {
    it("points at the routes of the results router", () => {
        expect(ResultsRoutes).toEqual({
            test: "/api/v1/results/test",
            createGraphView: "/api/v1/results/graph-view/create",
            updateGraphView: "/api/v1/results/graph-view/update",
        });
    });
});
