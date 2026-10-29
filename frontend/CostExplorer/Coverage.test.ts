import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/svelte";

import Coverage from "./Coverage.svelte";

afterEach(cleanup);

describe("Coverage.svelte", () => {
    it("lists the runs that carry only an estimate under the no-data count", () => {
        render(Coverage, { props: { coverage: { complete: 1, partial: 0, none: 2, estimate_only: { count: 2, spend: 850 } } } });

        expect(screen.getByText("Estimate only")).toBeTruthy();
        expect(screen.getByText("2 · $850.00")).toBeTruthy();
    });

    it("omits the estimate line when every no-data run has none", () => {
        render(Coverage, { props: { coverage: { complete: 3, partial: 0, none: 1, estimate_only: { count: 0, spend: 0 } } } });

        expect(screen.queryByText("Estimate only")).toBeNull();
    });
});
