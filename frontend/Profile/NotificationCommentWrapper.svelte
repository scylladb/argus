<script>
    import Comment from "../Discussion/Comment.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    let users = $userList;
    export let supportData;
</script>

<Comment commentBody={supportData} {users} />
