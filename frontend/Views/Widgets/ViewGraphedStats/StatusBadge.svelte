<script lang="ts">
    import { NemesisStatusToTestStatus, StatusBackgroundCSSClassMap } from "../../../Common/TestStatus";
    import { subUnderscores, titleCase } from "../../../Common/TextUtils";
    import { TestRun } from "./Interfaces";

    export let run: TestRun;

    const status = run?.status || "";
</script>

<span class="badge {StatusBackgroundCSSClassMap[NemesisStatusToTestStatus[status] || status]}"
    >{subUnderscores(status)
        .split(" ")
        .map((v) => titleCase(v))
        .join(" ")}</span
>
