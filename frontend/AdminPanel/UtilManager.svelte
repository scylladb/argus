<script lang="ts">
    import { sendMessage } from "../Stores/AlertStore";

    const reloadConfig = async function () {
        try {
            const res = await fetch("/admin/api/v1/utils/config/reload", { method: "POST" });
            if (!res.ok) {
                throw new Error("Failed reloading the config: Transport Error");
            }
            const apiResponse = await res.json();
            if (apiResponse.status !== "ok") {
                throw apiResponse;
            }

            sendMessage("success", "Reloaded!");
        } catch (error) {
            if (error instanceof Error) {
                sendMessage("error", error.message);
            }
            console.log(error);
        }
    };

</script>


<div class="bg-white rounded p-2 shadow-sm my-2">
    <div>
        <h4>Utilities</h4>
    </div>
    <div>
        <button class="btn btn-primary" on:click={() => reloadConfig()}>Reload Config</button>
    </div>

</div>
