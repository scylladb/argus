import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import * as chrono from "chrono-node";
dayjs.extend(utc);

export const timestampToISODate = function(ts, includeSeconds = false) {
    const date = dayjs.utc(new Date(ts));

    let dateString = "YYYY-MM-DD HH:mm";
    dateString = includeSeconds ? dateString + ":ss" : dateString;

    return date.format(dateString);
};

export const generateWeeklyScheduleDate = function(today = new Date()) {
    let startingDay = chrono.parseDate("Last Friday at 00:00 UTC", new Date(today));
    return startingDay;
};

export const generateWeeklyScheduleEndDate = function(startDate) {
    let start = new Date(startDate);
    let end = chrono.parseDate("Next Thursday at 23:59 UTC", start);
    return end;
};


export const permanentScheduleStart = function(today = new Date()) {
    let startDate = dayjs.utc(today).subtract(1, "year");
    return startDate.toDate();
};


export const permanentScheduleEnd = function(today = new Date()) {
    let endDate = dayjs.utc(today).add(2, "year");
    return endDate.toDate();
};

export const startDate = function(release, today = new Date()) {
    return release?.perpetual ? generateWeeklyScheduleDate(today) : permanentScheduleStart(today);
};


export const endDate = function(release, startDate = new Date()) {
    return release?.perpetual ? generateWeeklyScheduleEndDate(startDate) : permanentScheduleEnd(startDate);
};
