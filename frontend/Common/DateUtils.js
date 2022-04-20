import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
dayjs.extend(utc);
export const timestampToISODate = function(ts, includeSeconds = false) {
    const date = dayjs.utc(new Date(ts));

    let dateString = `YYYY-MM-DD HH:mm`;
    dateString = includeSeconds ? dateString + `:ss` : dateString;

    return date.format(dateString);
}
