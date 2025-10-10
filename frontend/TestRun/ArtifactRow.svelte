<script lang="ts">
    import { onMount } from "svelte";
    import pretty from "prettysize";
    let { artifactName, artifactLink, originalLink } = $props();

    let artifactSize = $state();
    let downloadLinkElement: HTMLAnchorElement;

    const showArtifactSize = function (bytesCount) {
        if (!bytesCount) return "(N/A)";

        return `(${pretty(bytesCount)})`;
    };

    export const triggerDownload = () => {
        downloadLinkElement?.click();
    };

    onMount(async () => {
        let params = new URLSearchParams({
            l: originalLink
        });
        let res = await fetch("/api/v1/artifact/resolveSize?" + params);

        if (res.status != 200) return;
        let json = await res.json();
        if (json.status != "ok") {
            console.log(json.exception);
            return;
        }

        artifactSize = json.response.artifactSize;
    });
</script>


<tr>
    <td>{artifactName} <span class="fw-bold">{showArtifactSize(artifactSize)}</span></td>
    <td
        ><a
            bind:this={downloadLinkElement}
            class="btn btn-primary"
            href={artifactLink}>Download</a
        ></td
    >
</tr>
