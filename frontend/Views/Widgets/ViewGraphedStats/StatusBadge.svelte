<script lang="ts">
    import { NemesisStatusToTestStatus, StatusBackgroundCSSClassMap } from "../../../Common/TestStatus";
    import { subUnderscores, titleCase } from "../../../Common/TextUtils";
    import { TestRun } from "./Interfaces";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    const status = run?.status || "";
</script>

<span class="badge {StatusBackgroundCSSClassMap[NemesisStatusToTestStatus[status] || status]}"
    >{subUnderscores(status)
        .split(" ")
        .map((v) => titleCase(v))
        .join(" ")}</span
>
