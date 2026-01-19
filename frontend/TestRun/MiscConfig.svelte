<script lang="ts">
    let {
        name,
        content,
    }: {
        name: string,
        content: string,
    } = $props();

</script>

<div>
    <h4>{name}</h4>
    <pre class="code border p-2 rounded bg-light-one" style="white-space: pre-wrap;">{content}</pre>
</div>
