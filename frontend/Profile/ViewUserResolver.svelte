<script>
    import { userList } from "../Stores/UserlistSubscriber";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";

    /**
     * @type {Element}
     */
    export let element;
    let creatorId = element.dataset.argusViewCreator;
</script>

<div class="d-inline-block">
    <AssigneeList assignees={[creatorId]} />
</div>
