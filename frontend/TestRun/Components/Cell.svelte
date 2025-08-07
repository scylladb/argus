<script lang="ts">
    type Cell = {
        value?: string | number;
        value_text?: string;
        type?: string;
    };

    type CellType = "NUMBER" | "TEXT" | "LINK" | "IMAGE";
    interface Props {
        cell: Cell;
        selectedScreenshot: string;
    }

    let { cell, selectedScreenshot = $bindable() }: Props = $props();
    let value: string = $state();
    let type: CellType = $state("TEXT");
    const durationToStr = (seconds: number) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
    };
    if (cell?.value === undefined || cell?.value === null) {
        type = "TEXT";
        value = "N/A";
    } else if (typeof cell.value === "string") {
        value = cell.value;
        const urlRegex = /^(https?:\/\/[^\s]+)/i; // Ensure the entire string is a URL
        const imageRegex = /\.(jpeg|jpg|gif|png|bmp|svg)$/i;

        const isUrl = urlRegex.test(value);
        const isImage = isUrl && imageRegex.test(value); // Checks if it's a URL and ends with an image extension

        type = isImage ? "IMAGE" : isUrl ? "LINK" : "TEXT";
    } else {
        const value_number = cell.value;
        type = "NUMBER";
        switch (cell.type) {
        case "FLOAT":
            value = String(value_number.toFixed(2));
            break;
        case "INTEGER":
            value = String(value_number.toLocaleString());
            break;
        case "DURATION":
            value = String(durationToStr(value_number));
            break;
        default:
            value = String(value_number);
        }
    }
</script>

{#if type === "NUMBER" || type === "TEXT"}
    {value}
{:else if type === "LINK"}
    <a href="{value}" target="_blank" rel="noopener noreferrer">link</a>
{:else if type === "IMAGE"}
    <button class="btn btn-primary btn-sm py-0" onclick={() => selectedScreenshot = value} data-link="{value}">view</button>
{/if}
