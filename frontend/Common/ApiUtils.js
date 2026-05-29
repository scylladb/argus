import { sendMessage } from "../Stores/AlertStore";

export const apiMethodCall = async function (endpoint, body, method = "POST") {
    try {
        let apiResponse = await fetch(endpoint, {
            method: method,
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        });
        let res = await apiResponse.json();
        if (res.status === "ok") {
            return res;
        } else {
            throw res;
        }
    } catch (error) {
        if (error?.status === "error") {
            sendMessage(
                "error",
                `API Error.\nMessage: ${error.response.arguments[0]}`,
                "apiMethodCall"
            );
        } else {
            sendMessage(
                "error",
                "Unhandled API Error occured. \nCheck console for details.",
                "apiMethodCall"
            );
            console.log(error);
        }
    } finally {

    }
};

/**
 * Fetch a JSON endpoint that returns the standard Argus {status, response} envelope.
 * Throws on non-OK HTTP status or when the API returns status !== "ok".
 * @template T
 * @param {string} url
 * @param {RequestInit} [init]
 * @returns {Promise<T>}
 */
export const fetchJson = async (url, init) => {
    const response = await fetch(url, init);
    const data = await response.json().catch(() => null);
    if (!data) {
        throw new Error(`HTTP ${response.status} on ${url}`);
    }
    if (data.status !== "ok") {
        const message =
            data.message ??
            data.response?.arguments?.[0] ??
            data.response?.message ??
            `HTTP ${response.status}`;
        throw new Error(message);
    }
    return data.response;
};
