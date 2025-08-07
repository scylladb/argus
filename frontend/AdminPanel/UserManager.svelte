<script>
    import Fa from "svelte-fa";
    import { faTimes } from "@fortawesome/free-solid-svg-icons";
    import { getPicture } from "../Common/UserUtils";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    import { titleCase } from "../Common/TextUtils";


    let users = [];
    let lastError = $state("");
    let selectedUser = $state();
    let working = $state(false);
    let confirmChangePassword = $state(false);
    let confirmToggleAdmin = $state(false);
    let confirmDeleteUser = $state(false);
    let confirmChangeEmail = $state(false);
    let newEmail = $state("");
    let newPassword = $state("");
    let newPasswordConfirm = $state("");
    let userDeleteConfirmationUsername = $state("");

    const getUsers = async function() {
        let response = await fetch("/admin/api/v1/users");
        if (response.status != 200) throw new Error("HTTP Transport error: Failed fetching users.");

        let data = await response.json();
        if (data.status !== "ok") throw new Error(data.response.arguments[0]);

        users = Object.values(data.response).sort((userLeft, userRight) => {
            const lhs = (userLeft.full_name || userLeft.username).toLowerCase();
            const rhs = (userRight.full_name || userRight.username).toLowerCase();
            if (lhs > rhs) {
                return 1;
            } else if (lhs < rhs) {
                return -1;
            }
            return 0;
        });

        return users;
    };

    const invalidateUsers = function() {
        userPromise = getUsers();
    };

    const resetState = function() {
        selectedUser = undefined;
        working = false;
    };

    let userPromise = $state(getUsers());

    const changeUserPassword = async function() {
        try {
            working = true;
            if (newPassword != newPasswordConfirm) throw new Error("Passwords do not match!");
            let response = await fetch(
                `/admin/api/v1/user/${selectedUser.id}/password/set`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        newPassword: newPassword
                    })
                }
            );
            if (response.status != 200) throw new Error("HTTP Transport error: Failed changing password");

            let data = await response.json();
            if (data.status !== "ok") throw new Error(data.response.arguments[0]);

            return true;
        } catch (error) {
            lastError = error.message;
        } finally {
            confirmChangePassword = false;
            newPassword = "";
            newPasswordConfirm = "";
            resetState();
        }
    };

    const changeUserEmail = async function() {
        try {
            working = true;
            let response = await fetch(
                `/admin/api/v1/user/${selectedUser.id}/email/set`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        newEmail: newEmail
                    })
                }
            );
            if (response.status != 200) throw new Error("HTTP Transport error: Failed changing the email.");

            let data = await response.json();
            if (data.status !== "ok") throw new Error(data.response.arguments[0]);

            return true;
        } catch (error) {
            lastError = error.message;
        } finally {
            confirmChangeEmail = false;
            resetState();
            invalidateUsers();
        }
    };

    const deleteUser = async function() {
        try {
            working = true;
            let response = await fetch(
                `/admin/api/v1/user/${selectedUser.id}/delete`,
                {
                    method: "POST"
                }
            );
            if (response.status != 200) throw new Error("HTTP Transport error: Failed deleting the user.");

            let data = await response.json();
            if (data.status !== "ok") throw new Error(data.response.arguments[0]);

            return true;
        } catch (error) {
            lastError = error.message;
        } finally {
            confirmDeleteUser = false;
            resetState();
            invalidateUsers();
        }
    };

    const toggleUserAdmin = async function() {
        try {
            working = true;
            let response = await fetch(
                `/admin/api/v1/user/${selectedUser.id}/admin/toggle`,
                {
                    method: "POST"
                }
            );
            if (response.status != 200) throw new Error("HTTP Transport error: Failed setting user as admin.");

            let data = await response.json();
            if (data.status !== "ok") throw new Error(data.response.arguments[0]);

            return true;
        } catch (error) {
            lastError = error.message;
        } finally {
            confirmToggleAdmin = false;
            resetState();
            invalidateUsers();
        }
    };

    const isAdmin = function (user) {
        return user.roles.includes("ROLE_ADMIN");
    };

</script>

{#if confirmChangeEmail}
    <ModalWindow on:modalClose={() => confirmChangeEmail = false}>
        {#snippet title()}
                <div >Changing email for <span class="fw-bold">@{selectedUser.username}</span></div>
            {/snippet}
        {#snippet body()}
                <div >
                <div class="form-group">
                    <label for="changeEmailField" class="form-label">New Email</label>
                    <input id="changeEmailField" type="email" class="form-control" bind:value={newEmail}>
                </div>
                <div class="d-flex align-items-center my-2">
                    <button disabled={working} class="btn btn-primary w-75 me-2" onclick={changeUserEmail}>Confirm</button>
                    <button disabled={working} class="btn btn-secondary w-25" onclick={() => confirmChangeEmail = false}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}
{#if confirmChangePassword}
    <ModalWindow on:modalClose={() => confirmChangePassword = false}>
        {#snippet title()}
                <div >Changing password for <span class="fw-bold">@{selectedUser.username}</span></div>
            {/snippet}
        {#snippet body()}
                <div >
                <div class="form-group">
                    <label for="changePasswordField" class="form-label">New Password</label>
                    <input id="changePasswordField" type="password" class="form-control" bind:value={newPassword}>
                </div>
                <div class="form-group">
                    <label for="changeConfirmPasswordField" class="form-label">Confirm Password</label>
                    <input id="changeConfirmPasswordField" type="password" class="form-control" bind:value={newPasswordConfirm}>
                </div>
                <div class="d-flex align-items-center my-2">
                    <button disabled={working} class="btn btn-primary w-75 me-2" onclick={changeUserPassword}>Confirm</button>
                    <button disabled={working} class="btn btn-secondary w-25" onclick={() => confirmChangePassword = false}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if confirmDeleteUser}
    <ModalWindow on:modalClose={() => confirmDeleteUser = false}>
        {#snippet title()}
                <div >Deleting <span class="fw-bold">@{selectedUser.username}</span></div>
            {/snippet}
        {#snippet body()}
                <div >
                <div>
                    Are you sure you want to delete <span class="fw-bold">@{selectedUser.username}</span>?
                </div>
                <div class="form-group">
                    <label for="deleteUserConfirm" class="form-label">Type the username to confirm</label>
                    <input id="deleteUserConfirm" type="text" class="form-control" bind:value={userDeleteConfirmationUsername}>
                </div>
                <div class="d-flex align-items-center my-2">
                    <button disabled={working || userDeleteConfirmationUsername != selectedUser.username} class="btn btn-danger w-75 me-2" onclick={deleteUser}>Confirm</button>
                    <button disabled={working} class="btn btn-secondary w-25" onclick={() => confirmDeleteUser = false}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if confirmToggleAdmin}
    <ModalWindow on:modalClose={() => confirmToggleAdmin = false}>
        {#snippet body()}
                <div >
                <div>
                    {#if isAdmin(selectedUser)}
                        Are you sure you want to demote <span class="fw-bold">@{selectedUser.username}</span> from <span class="text-danger">Admin</span> role?
                    {:else}
                        Are you sure you want to set <span class="fw-bold">@{selectedUser.username}</span> as <span class="text-danger">Admin</span>?
                    {/if}
                </div>
                <div class="d-flex align-items-center my-2">
                    <button disabled={working} class="btn btn-warning w-75 me-2" onclick={toggleUserAdmin}>Confirm</button>
                    <button disabled={working} class="btn btn-secondary w-25" onclick={() => {
                    invalidateUsers();
                    confirmToggleAdmin = false;
                }}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

<div>
    <div class="bg-white rounded m-2">
        {#if lastError}
            <div class="p-2">
                <div class="alert alert-danger d-flex align-items-center">
                    <div>{lastError}</div>
                    <div class="text-end ms-auto">
                        <button class="btn" onclick={() => lastError = ""}><Fa icon={faTimes} /></button>
                    </div>
                </div>
            </div>
        {/if}
        {#await userPromise}
            <div class="p-2 text-center text-muted">
                <span class="spinner-border spinner-border-sm"></span> Loading users...
            </div>
        {:then userList}
            <ul class="list-group list-group-flush rounded">
                {#each userList as user (user.id)}
                    <li class="list-group-item">
                        <div class="d-flex align-items-center">
                            <div>
                                <img class="img-profile" src="{getPicture(user.picture_id)}" alt="">
                            </div>
                            <div class="ms-2">
                                <div>{user.full_name || titleCase(user.username)}</div>
                                <div class="text-muted text-sm">@{user.username}</div>
                                <div class="text-muted text-sm">{user.email}</div>
                                {#if user.registration_date}
                                    <div class="text-muted text-sm">
                                        Created on {timestampToISODate(Date.parse(user.registration_date))}
                                    </div>
                                {/if}
                            </div>
                            <div class="ms-auto">
                                <div class="form-check form-switch">
                                    <input
                                        disabled={working}
                                        class="form-check-input"
                                        type="checkbox"
                                        role="switch"
                                        title="Switch user admin state"
                                        checked={isAdmin(user)}
                                        onchange={() => {
                                            selectedUser = user;
                                            confirmToggleAdmin = true;
                                        }}
                                        id="userToggleAdmin-{user.id}"
                                    />
                                    <label
                                        class="form-check-label"
                                        for="userToggleAdmin-{user.id}">Admin</label
                                    >
                                </div>
                            </div>
                            <div class="ms-2">
                                <div class="d-flex align-items-center btn-group">
                                    <button
                                        disabled={working}
                                        class="btn btn-outline-primary"
                                        onclick={() => {
                                            selectedUser = user;
                                            newEmail = user.email;
                                            confirmChangeEmail = true;
                                        }}>
                                        Change Email
                                    </button>
                                    <button
                                        disabled={working}
                                        class="btn btn-outline-primary"
                                        onclick={() => {
                                            selectedUser = user;
                                            confirmChangePassword = true;
                                        }}>
                                        Change Password
                                    </button>
                                    <button
                                        disabled={working}
                                        class="btn btn-outline-danger"
                                        onclick={() => {
                                            selectedUser = user;
                                            confirmDeleteUser = true;
                                        }}>
                                        Delete User
                                    </button>
                                </div>
                            </div>
                        </div>
                    </li>
                {/each}
            </ul>
        {:catch error}
            <div>
                <div class="alert alert-danger">
                    {error.message}
                </div>
            </div>
        {/await}
    </div>
</div>


<style>
    .text-sm {
        font-size: 0.8em;
    }

    .img-profile {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background-color: rgb(163, 163, 163);
        background-clip: border-box;
        background-repeat: no-repeat;
        background-position: center;
        background-size: cover;
    }
</style>
