export const filterUser = function (label, filterText, user) {
    return `${label ?? ""}${user?.full_name ?? ""}`.toLowerCase().includes(filterText.toLowerCase());
};
