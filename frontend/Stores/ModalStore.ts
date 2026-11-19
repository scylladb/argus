import { writable } from "svelte/store";

export const openModals = writable<HTMLDialogElement[]>([]);

export const addModal = (dialog: HTMLDialogElement) => openModals.update((dialogs) => [...dialogs, dialog]);

export const removeModal = (dialog: HTMLDialogElement) =>
    openModals.update((dialogs) => dialogs.filter((open) => open !== dialog));
