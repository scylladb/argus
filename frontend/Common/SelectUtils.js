import * as urlSlug from "url-slug";

export const filterUser = function (label, filterText, user) {
    const term = `${label ?? ""}${user?.full_name ?? ""}`;
    const normalizedTerm = urlSlug.convert(term, {
        separator: " ",
        transformer: urlSlug.LOWERCASE_TRANSFORMER,
        dictionary: {
            Ł: "L",
            ł: "l",
        }
    });
    return normalizedTerm.includes(filterText.toLowerCase());
};
