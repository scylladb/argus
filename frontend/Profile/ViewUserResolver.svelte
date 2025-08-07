<script>
    import { userList } from "../Stores/UserlistSubscriber";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";


    /**
     * @typedef {Object} Props
     * @property {Element} element
     */

    /** @type {Props} */
    let { element } = $props();
    let creatorId = element.dataset.argusViewCreator;
</script>

<div class="d-inline-block">
    <AssigneeList assignees={[creatorId]} />
</div>
