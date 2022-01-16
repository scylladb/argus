<script>
    import { sendMessage, alertStore } from "../Stores/AlertStore.js";

    alertStore.subscribe((value) => {
        console.log(value);
    });

</script>

<button
    id="storeSuccess"
    class="btn btn-success"
    on:click={() => {

    }}>Store Success</button
>
<button
    id="storeError"
    class="btn btn-danger"
    on:click={() => {
        sendMessage("error", "Wowe it doesn't work.");
    }}>Store Error</button
>
